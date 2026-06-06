#!/usr/bin/env python3
"""
PACS 集成API — 双向数据通道

PACS → 超声系统 (获取PACS数据):
  POST /api/pacs/patient/lookup   — 根据门诊号/住院号查询患者
  POST /api/pacs/worklist         — 获取待检列表 (worklist)

超声系统 → PACS (回传报告):
  POST /api/pacs/report/send      — 发送结构化报告到 PACS
  GET  /api/reports/export/{id}   — 导出报告为 PACS 兼容格式 (HL7/JSON)

鉴权: 所有接口需 Bearer Token (api_platform 的 API Key)
"""

import json, re, logging
from datetime import datetime
from pathlib import Path
from fastapi import APIRouter, HTTPException, Request, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

import db
from api_platform.auth import verify_api_key

_log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/pacs", tags=["PACS集成"])

# ── Models ──

class PatientLookupRequest(BaseModel):
    """根据门诊号/住院号/身份证查患者"""
    outpatient_no: str | None = Field(None, description="门诊号")
    inpatient_no: str | None = Field(None, description="住院号")
    id_card: str | None = Field(None, description="身份证号")
    name: str | None = Field(None, description="患者姓名(模糊匹配)")

class WorklistRequest(BaseModel):
    """获取待检列表"""
    exam_type: str | None = Field(None, description="检查类型: 腹部超声/心脏超声/...")
    date_from: str | None = Field(None, description="开始日期 YYYY-MM-DD")
    date_to: str | None = Field(None, description="结束日期 YYYY-MM-DD")
    status: str | None = Field("待检", description="状态: 待检/检查中/已完成")
    limit: int = Field(20, ge=1, le=200)

class ReportSendRequest(BaseModel):
    """回传报告到 PACS"""
    outpatient_no: str | None = Field(None, description="门诊号")
    inpatient_no: str | None = Field(None, description="住院号")
    exam_date: str = Field(..., description="检查日期 YYYY-MM-DD")
    exam_time: str | None = Field(None, description="检查时间 HH:MM:SS")
    machine_type: str | None = Field("彩超", description="设备类型")
    exam_part: str | None = Field(None, description="检查部位/脏器")
    describes: str = Field(..., min_length=2, description="超声所见")
    diagnosis: str | None = Field(None, description="超声提示")
    template_name: str | None = Field(None, description="模板名称")
    patient_name: str | None = Field(None)
    patient_sex: str | None = Field(None)
    patient_age: int | None = Field(None)
    report_id: int | None = Field(None, description="系统内部报告ID(如有)")

# ── Token 鉴权中间件 ──

async def _auth(request: Request):
    """从 Header 验证 API Key"""
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(401, "Missing Bearer token")
    token = auth_header[7:]
    tenant = verify_api_key(token)
    if not tenant:
        raise HTTPException(403, "Invalid API key")
    return tenant

# ═══════════════════════════════════════════
# PACS → 超声系统
# ═══════════════════════════════════════════

@router.post("/patient/lookup")
async def pacs_patient_lookup(req: PatientLookupRequest, request: Request):
    """
    PACS 调用此接口查询患者信息。
    根据门诊号/住院号返回患者基本信息和已有检查记录。
    """
    tenant = await _auth(request)
    _log.info(f"[PACS] patient_lookup tenant={tenant['id']} outpatient={req.outpatient_no}")

    # 查询本地患者
    patient = None
    if req.outpatient_no:
        patient = db.patient_find_by_outpatient(req.outpatient_no)
    if not patient and req.inpatient_no:
        patient = db.patient_find_by_inpatient(req.inpatient_no)
    if not patient and req.name:
        patients = db.patient_search_by_name(req.name)
        if patients: patient = patients[0]

    if not patient:
        return JSONResponse({
            "success": False,
            "message": "患者未找到",
            "patient": None,
        })

    # 查该患者的历史报告
    reports = db.report_list_by_patient(patient['id'], limit=5)

    return JSONResponse({
        "success": True,
        "patient": {
            "id": patient['id'],
            "name": patient['name'],
            "gender": patient.get('gender', ''),
            "age": patient.get('age'),
            "exam_type": patient.get('exam_type', ''),
            "outpatient_no": patient.get('outpatient_id', ''),
            "inpatient_no": patient.get('inpatient_id', ''),
            "department": patient.get('department', ''),
            "clinical_diag": patient.get('clinical_diag', ''),
        },
        "reports": [
            {
                "id": r['id'],
                "template": r.get('template', ''),
                "exam_date": r.get('created_at', '')[:10],
                "describes": r.get('describes', r.get('structured', {}).get('report', {}).get('study_see', ''))[:200],
                "diagnosis": r.get('diagnosis', ''),
            }
            for r in reports
        ],
    })


@router.post("/worklist")
async def pacs_worklist(req: WorklistRequest, request: Request):
    """
    PACS 调用此接口获取待检查患者列表 (Worklist)。
    超声工作站可定时轮询此接口获取新任务。
    """
    tenant = await _auth(request)
    _log.info(f"[PACS] worklist tenant={tenant['id']} exam={req.exam_type}")

    patients = db.patient_queue(
        exam_type=req.exam_type,
        status=req.status or "待检",
        date_from=req.date_from,
        date_to=req.date_to,
        limit=req.limit,
    )

    items = []
    for p in patients:
        items.append({
            "patient_id": p['id'],
            "name": p['name'],
            "gender": p.get('gender', ''),
            "age": p.get('age'),
            "exam_type": p.get('exam_type', ''),
            "exam_part": p.get('exam_part', ''),
            "status": p.get('status', ''),
            "outpatient_no": p.get('outpatient_id', ''),
            "inpatient_no": p.get('inpatient_id', ''),
            "department": p.get('department', ''),
            "clinical_diag": p.get('clinical_diag', ''),
        })

    return JSONResponse({
        "success": True,
        "count": len(items),
        "worklist": items,
    })

# ═══════════════════════════════════════════
# 超声系统 → PACS
# ═══════════════════════════════════════════

@router.post("/report/send")
async def pacs_report_send(req: ReportSendRequest, request: Request):
    """
    超声系统调用此接口将报告发送到 PACS。
    PACS 收到后会存入 HL7/DICOM SR 格式。
    """
    tenant = await _auth(request)
    _log.info(f"[PACS] report_send tenant={tenant['id']} outpatient={req.outpatient_no}")

    # 存入 api_reports 表 (PACS 标准格式)
    report_id = db.api_report_insert(
        examdate=req.exam_date,
        examtime=req.exam_time,
        machinetype=req.machine_type or "彩超",
        visceras=req.exam_part,
        name=req.patient_name,
        sex=req.patient_sex,
        age=req.patient_age,
        describes=req.describes,
        diagnosis=req.diagnosis,
        module_name=req.template_name,
        outpatient_no=req.outpatient_no,
        inpatient_no=req.inpatient_no,
        tenant_id=tenant['id'],
        internal_report_id=req.report_id,
    )

    # 生成 PACS 兼容的 HL7 ORU^R01 格式
    hl7_msg = _build_hl7_oru(req, report_id)

    db.audit_log(
        "pacs_send",
        patient_id=req.outpatient_no,
        input_text=json.dumps(req.model_dump(), ensure_ascii=False)[:500],
        output_text=f"report_id={report_id}",
        detail={"hl7_length": len(hl7_msg)},
    )

    return JSONResponse({
        "success": True,
        "report_id": report_id,
        "message": "报告已发送至PACS",
        "hl7_message": hl7_msg[:500] if hl7_msg else None,  # 调试用, 生产可关闭
    })


@router.get("/report/export/{report_id}")
async def pacs_report_export(report_id: int, format: str = Query("json", description="json|hl7|dicomxml"), request: Request = None):
    """
    导出指定报告为 PACS 兼容格式。
    - json: 简化 JSON
    - hl7:   HL7 ORU^R01 格式
    - dicomxml: DICOM SR XML (简化)
    """
    tenant = await _auth(request)
    report = db.api_report_get(report_id)
    if not report:
        raise HTTPException(404, "报告不存在")
    if report.get('tenant_id') != tenant['id']:
        raise HTTPException(403, "无权访问此报告")

    if format == "hl7":
        req = ReportSendRequest(
            exam_date=report['examdate'] or '',
            exam_time=report.get('examtime'),
            describes=report['describes'] or '',
            diagnosis=report.get('diagnosis', ''),
            template_name=report.get('module_name', ''),
            patient_name=report.get('name', ''),
            patient_sex=report.get('sex', ''),
            patient_age=report.get('age'),
            outpatient_no=report.get('outpatient_no', ''),
            inpatient_no=report.get('inpatient_no', ''),
            machine_type=report.get('machinetype', '彩超'),
            exam_part=report.get('visceras', ''),
        )
        return JSONResponse({
            "success": True,
            "format": "hl7",
            "content": _build_hl7_oru(req, report_id),
        })

    elif format == "json" or format == "dicomxml":
        return JSONResponse({
            "success": True,
            "report": report,
            "format": format,
        })

    raise HTTPException(400, f"不支持格式: {format}")


# ── HL7 ORU^R01 构建 ──
def _build_hl7_oru(req: ReportSendRequest, report_id: int) -> str:
    """构建简化的 HL7 ORU^R01 消息"""
    now = datetime.now()
    msh = [
        "MSH|^~\\&|ULTRASOUND|HOSPITAL|PACS|HOSPITAL",
        f"{now.strftime('%Y%m%d%H%M%S')}||ORU^R01|{report_id}|P|2.5",
    ]
    pid = [
        "PID|1",
        f"|||{req.outpatient_no or ''}||{req.patient_name or ''}",
        f"||||{req.patient_sex or ''}||{req.patient_age or ''}",
    ]
    obr = [
        "OBR|1",
        f"|||超声检查^{req.exam_part or ''}",
        f"||||{req.exam_date}",
    ]
    obx = [
        "OBX|1|TX",
        f"|超声所见|{req.describes[:200]}",
    ]
    if req.diagnosis:
        obx.append(f"OBX|2|TX|超声提示|{req.diagnosis}")

    return "\r".join("|".join(seg) for seg in [msh, pid, obr, obx])


# ── 报告同步状态查询 ──

@router.get("/report/status/{report_id}")
async def pacs_report_status(report_id: int, request: Request):
    """查询报告是否已成功发送到 PACS"""
    tenant = await _auth(request)
    report = db.api_report_get(report_id)
    if not report:
        raise HTTPException(404, "报告不存在")

    # 从 audit_log 查 pacs_send 记录
    logs = db.audit_log_query(action="pacs_send", report_id=report_id, limit=1)

    return JSONResponse({
        "success": True,
        "report_id": report_id,
        "sent": len(logs) > 0,
        "sent_at": logs[0].get('created_at', '') if logs else None,
        "report_status": report.get('status', 'unknown'),
    })
