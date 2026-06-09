"""
超声语音报告系统 - 报告 CRUD 路由 (使用 db.py 数据层)
(从 main.py 拆出的内联路由，区别于 routers/reports.py 使用 database.py)
"""
import logging
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

import db

router = APIRouter(tags=["报告管理"])


class ReportUpdateRequest(BaseModel):
    raw_text: str | None = None
    structured: dict | None = None
    edited: dict | None = None
    status: str | None = None


def _filter_checked(report: dict) -> dict:
    """过滤掉 unchecked 的 study_hint 条目"""
    r = dict(report)
    r["study_hint"] = [
        {k: v for k, v in h.items() if k not in ("id", "checked")}
        for h in report.get("study_hint", []) if h.get("checked", True)
    ]
    return r


@router.get("/api/reports/{report_id}")
async def get_report(report_id: int):
    r = db.report_get(report_id)
    if not r:
        raise HTTPException(404, "报告不存在")
    return {"success": True, "report": r}


@router.put("/api/reports/{report_id}")
async def update_report(report_id: int, req: ReportUpdateRequest):
    r = db.report_update(report_id, raw_text=req.raw_text,
                         structured=req.structured, edited=req.edited,
                         status=req.status)
    if not r:
        raise HTTPException(404, "报告不存在")
    return {"success": True, "report": r}


@router.post("/api/reports/{report_id}/save")
async def save_report(report_id: int, report: dict | None = None):
    """保存报告（只保存 checked=true 的内容）+ 操作留痕"""
    if not report:
        raise HTTPException(400, "报告数据为空")
    inner = report.get("report") if isinstance(report.get("report"), dict) else None
    data = inner if inner else report
    cleaned = _filter_checked(data)
    r = db.report_update(report_id, edited=cleaned)
    if not r:
        raise HTTPException(404, "报告不存在")
    db.audit_log("doctor_save", patient_id=r.get("patient_id"),
                 input_text=str(data)[:200], output_text="saved",
                 detail={"report_id": report_id})
    return {"success": True, "report": r, "message": "报告已保存"}


@router.post("/api/reports/{report_id}/send")
async def send_report(report_id: int, report: dict | None = None):
    """发送报告到 PACS + 操作留痕"""
    if not report:
        raise HTTPException(400, "报告数据不能为空")
    inner = report.get("report") if isinstance(report, dict) and isinstance(report.get("report"), dict) else None
    data = inner if inner else report
    cleaned = _filter_checked(data) if data else None
    r = db.report_confirm(report_id, cleaned or {})
    if not r:
        raise HTTPException(404, "报告不存在")
    logging.info(f"[PACS] 发送报告 report_id={report_id} patient_id={r['patient_id']}")
    db.audit_log("pacs_send", patient_id=r.get("patient_id"),
                 input_text=str(data)[:200], output_text="sent",
                 detail={"report_id": report_id})
    return {"success": True, "message": "报告已保存并发送至PACS（Mock）", "report_id": report_id}


@router.post("/api/reports/{report_id}/confirm")
async def confirm_report(report_id: int, edited: dict | None = None):
    r = db.report_confirm(report_id, edited or {})
    if not r:
        raise HTTPException(404, "报告不存在")
    return {"success": True, "report": r}
