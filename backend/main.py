"""超声报告语音结构化 MVP — FastAPI 后端 v0.3"""

from dotenv import load_dotenv
from pathlib import Path
load_dotenv(Path(__file__).resolve().parents[2] / ".env")

import os
import uuid
import logging
from datetime import datetime

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

from asr_client import transcribe_audio
from llm_client import structure_report as llm_structure
from templates import match_template, TEMPLATES
import db

app = FastAPI(title="超声报告语音结构化", version="0.3.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"],
)

AUDIO_DIR = Path(__file__).parent / "audio_backups"
AUDIO_DIR.mkdir(exist_ok=True)

# ==================== 通用 ====================

@app.get("/api/health")
async def health():
    return {"status": "ok", "version": "0.3.0"}

@app.get("/api/templates")
async def list_templates():
    return {k: {"name": v["name"], "organs": v["organs"]} for k, v in TEMPLATES.items()}

# ==================== 患者管理 ====================

class PatientAddRequest(BaseModel):
    name: str; gender: str; age: int; exam_type: str; exam_part: str = None

@app.post("/api/patients/quick-add")
async def patient_quick_add(req: PatientAddRequest):
    if not req.name.strip(): raise HTTPException(400, "姓名不能为空")
    if req.gender not in ("男","女"): raise HTTPException(400, "性别只能为 男 或 女")
    if req.age < 0 or req.age > 200: raise HTTPException(400, "年龄不合法")
    if not req.exam_type.strip(): raise HTTPException(400, "检查类型不能为空")
    patient = db.patient_add(req.name.strip(), req.gender, req.age, req.exam_type.strip(), req.exam_part)
    return {"success": True, "patient": patient}

@app.get("/api/patients/queue")
async def patient_queue():
    return {"success": True, "patients": db.patient_queue()}

@app.put("/api/patients/{patient_id}/status")
async def patient_update_status(patient_id: int, status: str = "检查中"):
    p = db.patient_update_status(patient_id, status)
    if not p: raise HTTPException(404, "患者不存在")
    return {"success": True, "patient": p}

# ==================== 音频（持久化+回放） ====================

@app.post("/api/audio/upload")
async def audio_upload(file: UploadFile = File(...)):
    """上传原始录音到磁盘，返回 audio_id 供回放"""
    audio_bytes = await file.read()
    if len(audio_bytes) < 1024: raise HTTPException(400, "音频文件过小")
    if len(audio_bytes) > 50 * 1024 * 1024: raise HTTPException(400, "音频文件过大")

    audio_id = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
    suffix = Path(file.filename).suffix or ".webm"
    fname = f"{audio_id}{suffix}"
    fpath = AUDIO_DIR / fname

    with open(fpath, "wb") as f:
        f.write(audio_bytes)

    return {"success": True, "audio_id": audio_id, "filename": fname, "size": len(audio_bytes)}

@app.get("/api/audio/{audio_id}")
async def audio_playback(audio_id: str):
    """回放原始录音"""
    matches = list(AUDIO_DIR.glob(f"{audio_id}.*"))
    if not matches: raise HTTPException(404, "音频文件不存在")
    return FileResponse(matches[0])

# ==================== 语音转写 ====================

@app.post("/api/transcribe")
async def transcribe(file: UploadFile = File(...)):
    """上传音频，返回转写文本 + audio_id"""
    if not file.filename: raise HTTPException(400, "文件格式不识别")
    audio_bytes = await file.read()
    if len(audio_bytes) < 1024: raise HTTPException(400, "音频文件过小")
    if len(audio_bytes) > 50 * 1024 * 1024: raise HTTPException(400, "音频文件过大")

    # 备份
    suffix = Path(file.filename).suffix or ".wav"
    backup_name = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}{suffix}"
    backup_path = AUDIO_DIR / backup_name
    audio_id = backup_name.rsplit(".", 1)[0]
    try:
        with open(backup_path, "wb") as f: f.write(audio_bytes)
    except OSError:
        backup_path = None
        audio_id = None

    # 转写
    try:
        text = await transcribe_audio(audio_bytes)
    except Exception as e:
        raise HTTPException(500, f"语音识别失败: {e}")

    return {"success": True, "text": text, "audio_id": audio_id}

# ==================== 结构化（含查勾卡片） ====================

class StructureRequest(BaseModel):
    text: str
    exam_type: str = "腹部超声"
    patient_id: int = None

def _wrap_hints_with_toggle(report: dict) -> dict:
    """给 study_hint 每条包裹 checked + id"""
    hints = report.get("study_hint", [])
    for i, h in enumerate(hints):
        h["id"] = f"h{i}"
        h["checked"] = True
    return report

def _filter_checked(report: dict) -> dict:
    """过滤掉 unchecked 的 study_hint 条目"""
    r = dict(report)
    r["study_hint"] = [
        {k: v for k, v in h.items() if k not in ("id", "checked")}
        for h in report.get("study_hint", []) if h.get("checked", True)
    ]
    return r

@app.post("/api/structure")
async def structure(req: StructureRequest):
    """结构化 + 包裹 toggle 字段（新版双层格式）"""
    if not req.text or not req.text.strip(): raise HTTPException(400, "文本为空")
    if len(req.text) > 10000: raise HTTPException(400, "文本过长")

    try:
        report = llm_structure(req.text, req.exam_type)
    except Exception as e:
        raise HTTPException(500, f"结构化失败: {e}")

    report = _wrap_hints_with_toggle(report)

    report_id = None
    if req.patient_id:
        try:
            r = db.report_create(req.patient_id, match_template(req.exam_type), req.text, _filter_checked(report))
            report_id = r["id"]
        except Exception as e:
            logging.exception("报告草稿保存失败")
            return {"success": True, "report": report, "report_id": None,
                    "warning": f"报告已生成但保存失败: {e}"}

    return {"success": True, "report": report, "report_id": report_id}

# ==================== 报告管理 ====================

class ReportUpdateRequest(BaseModel):
    raw_text: str = None; structured: dict = None; edited: dict = None; status: str = None

@app.get("/api/reports/{report_id}")
async def get_report(report_id: int):
    r = db.report_get(report_id)
    if not r: raise HTTPException(404, "报告不存在")
    return {"success": True, "report": r}

@app.put("/api/reports/{report_id}")
async def update_report(report_id: int, req: ReportUpdateRequest):
    r = db.report_update(report_id, raw_text=req.raw_text, structured=req.structured,
                         edited=req.edited, status=req.status)
    if not r: raise HTTPException(404, "报告不存在")
    return {"success": True, "report": r}

@app.post("/api/reports/{report_id}/save")
async def save_report(report_id: int, report: dict = None):
    """保存报告（只保存 checked=true 的内容）"""
    if not report: raise HTTPException(400, "报告数据为空")

    # 解包可能的嵌套结构（兼容结构返回时的 {"report": {...}} 包装）
    inner = report.get("report") if isinstance(report.get("report"), dict) else None
    data = inner if inner else report
    cleaned = _filter_checked(data)

    r = db.report_update(report_id, edited=cleaned, structured=cleaned)
    if not r: raise HTTPException(404, "报告不存在")
    return {"success": True, "report": r, "message": "报告已保存"}

@app.post("/api/reports/{report_id}/send")
async def send_report(report_id: int, report: dict = None):
    """发送报告到 PACS 超声报告数据库（当前为 mock）"""
    inner = report.get("report") if isinstance(report, dict) and isinstance(report.get("report"), dict) else None
    data = inner if inner else report
    cleaned = _filter_checked(data) if data else None
    # 1. 保存最终版
    r = db.report_confirm(report_id, cleaned or {})
    if not r: raise HTTPException(404, "报告不存在")

    # 2. 模拟 PACS 发送
    logging.info(f"[PACS] 发送报告 report_id={report_id} patient_id={r['patient_id']}")
    # TODO: 对接真实 PACS HL7/FHIR 接口
    # httpx.post(PACS_URL, json=hl7_message, headers=...)

    return {"success": True, "message": "报告已保存并发送至 PACS（Mock）", "report_id": report_id}

@app.post("/api/reports/{report_id}/confirm")
async def confirm_report(report_id: int, edited: dict = None):
    r = db.report_confirm(report_id, edited or {})
    if not r: raise HTTPException(404, "报告不存在")
    return {"success": True, "report": r}

# ==================== 静态文件 ====================

frontend_dir = Path(__file__).resolve().parent.parent / "frontend"

if frontend_dir.exists():
    @app.get("/")
    async def index():
        return FileResponse(frontend_dir / "index.html")

    @app.get("/{filename}")
    async def serve_static(filename: str):
        fpath = frontend_dir / filename
        if fpath.exists() and fpath.is_file(): return FileResponse(fpath)
        raise HTTPException(404)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8700, reload=True)
