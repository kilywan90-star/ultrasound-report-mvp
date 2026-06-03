"""超声报告语音结构化 MVP — FastAPI 后端 v0.3"""

from dotenv import load_dotenv
from pathlib import Path
# Try project root .env first, fall back to parent directory
_root = Path(__file__).resolve().parents[1]
_env = _root / ".env"
if not _env.exists():
    _env = Path(__file__).resolve().parents[2] / ".env"
load_dotenv(_env)

import os
import uuid
import logging
from datetime import datetime

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

try:
    from asr_client import transcribe_audio
    ASR_AVAILABLE = True
except (ImportError, ModuleNotFoundError):
    ASR_AVAILABLE = False
    async def transcribe_audio(*a, **kw): raise RuntimeError("ASR不可用")

from llm_client import structure_report as llm_structure
from templates import match_template, TEMPLATES
from template_filler import match_and_fill
from asr_correction import correct_ASR_text
from template_fetal import fill_fetal_template
from knowledge.loader import get_kb
import db

app = FastAPI(title="超声报告语音结构化")

# CORS: 允许常见来源但不回显任意Origin（避免creds问题）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)

# 安全响应头中间件
@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "microphone=(self)"
    return response

AUDIO_DIR = Path(__file__).parent / "audio_backups"
AUDIO_DIR.mkdir(exist_ok=True)

# ==================== 通用 ====================

@app.get("/api/health")
async def health():
    return {"status": "ok"}

@app.get("/api/templates")
async def list_templates():
    return {k: {"name": v["name"], "organs": v["organs"]} for k, v in TEMPLATES.items()}

# ==================== 患者管理 ====================

class PatientAddRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=50)
    gender: str
    age: int = Field(..., ge=0, le=150)
    exam_type: str = Field(..., min_length=1, max_length=50)
    exam_part: str = None

@app.post("/api/patients/quick-add")
async def patient_quick_add(req: PatientAddRequest):
    if not req.name.strip(): raise HTTPException(400, "姓名不能为空")
    if req.gender not in ("男","女"): raise HTTPException(400, "性别只能为 男 或 女")
    if req.age < 0 or req.age > 150: raise HTTPException(400, "年龄不合法(0-150)")
    if len(req.name.strip()) < 1: raise HTTPException(400, "姓名至少1个字符")
    if not req.exam_type.strip(): raise HTTPException(400, "检查类型不能为空")
    if len(req.exam_type.strip()) > 50: raise HTTPException(400, "检查类型过长(最多50字符)")
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
        result = await transcribe_audio(audio_bytes)
    except Exception as e:
        raise HTTPException(500, f"语音识别失败: {e}")

    return {"success": True, "raw_text": result["raw"], "text": result["text"], "audio_id": audio_id}

# ==================== 结构化（含查勾卡片） ====================

class StructureRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=10000)
    exam_type: str = Field(default="腹部超声", max_length=50)
    patient_id: str | None = None

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


def _confidence_score(report: dict) -> float:
    import re
    see = report.get("study_see", "")
    hints = report.get("study_hint", [])
    voice_count = len(re.findall(r'voice">([^<]+)<', see))
    unfill_count = see.count('unfill')
    total_fields = voice_count + unfill_count
    if total_fields == 0:
        return 0.0
    fill_ratio = voice_count / total_fields
    critical_fields = ['_bpd', '_hc', '_ac', '_fl', '_hr', '_bpd_ga']
    missing_critical = sum(1 for cf in critical_fields if '{'+cf+'}' in see)
    critical_ratio = (len(critical_fields) - missing_critical) / len(critical_fields) if len(critical_fields) > 0 else 0
    hint_score = min(len(hints) / 3, 1.0) if hints else 0.0
    return fill_ratio * 0.5 + critical_ratio * 0.4 + hint_score * 0.1

def _sanitize_pii(text: str, patient_id: str | None = None) -> str:
    """数据脱敏：移除姓名等PII后传给LLM"""
    if not patient_id:
        return text
    try:
        pid = int(patient_id)
        p = db.patient_get(pid)
        if p and p.get("name"):
            text = text.replace(p["name"], "[患者]")
    except (ValueError, Exception):
        pass
    return text


def _cross_validate(rule_report: dict, llm_report: dict, raw_text: str) -> dict:
    """一致性检查：LLM报告 vs 规则报告，补充遗漏字段"""
    if not rule_report or not llm_report:
        return llm_report or rule_report

    try:
        import re
        rule_see = rule_report.get("study_see", "")
        llm_see = llm_report.get("study_see", "")
        # 比较语音标记数量
        rule_voices = set(re.findall(r'voice\">([^<]+)<', rule_see))
        llm_voices = set(re.findall(r'voice\">([^<]+)<', llm_see))

        # 规则有但LLM没有的值 → 标记为需补充
        missing = rule_voices - llm_voices
        if missing and len(rule_voices) >= len(llm_voices):
            llm_report["_cross_check"] = {
                "rule_voices": len(rule_voices), "llm_voices": len(llm_voices),
                "missing_from_llm": list(missing), "recommendation": "规则库提取了更多值，建议使用规则结果"
            }
    except Exception:
        pass
    return llm_report


def _rule_fallback(raw_text: str, exam_type: str, patient_id: str | None) -> dict:
    """LLM不可用时的规则库兜底"""
    # 尝试胎儿模板
    if any(kw in (exam_type + (raw_text or "")[:80]) for kw in ["产科","胎儿","四维","排畸","孕","BPD","双顶径","股骨长","胎心"]):
        report = fill_fetal_template(raw_text)
        report = _wrap_hints_with_toggle(report)
    else:
        report = match_and_fill(raw_text, exam_type)
        if not report or not report.get("_template_matched"):
            report = {
                "patient_info": {"name": None, "gender": None, "age": None, "exam_id": None},
                "exam_info": {"modality": exam_type, "device": None, "exam_date": None},
                "study_see": f"<div class=\"rpt-html\">{raw_text}</div>",
                "study_hint": [],
                "recommendation": "规则库兜底生成，建议医生手动完善",
                "_template_matched": "rule_fallback",
            }
        report = _wrap_hints_with_toggle(report)
    report["_method"] = "rule_fallback"
    report.setdefault("study_hint", [])
    return report

@app.post("/api/structure")
async def structure(req: StructureRequest):
    """结构化：优先固定模板填充，降级到LLM自由生成"""
    if not req.text or not req.text.strip(): raise HTTPException(400, "文本为空")
    if len(req.text) > 10000: raise HTTPException(400, "文本过长")

    sanitized_text = _sanitize_pii(req.text, req.patient_id)

    # 策略0: 胎儿/产科超声 → 专用固定模板
    if any(kw in (req.exam_type + (req.text or "")[:80]) for kw in ["产科","胎儿","四维","排畸","孕","BPD","双顶径","股骨长","胎心"]):
        report = fill_fetal_template(correct_ASR_text(req.text))
        report = _wrap_hints_with_toggle(report)
        report_id = None
        if req.patient_id and req.patient_id.strip():
            try:
                pid = int(req.patient_id)
                r = db.report_create(pid, match_template(req.exam_type), req.text, _filter_checked(report))
                report_id = r["id"]
            except (ValueError, Exception):
                pass
        conf = _confidence_score(report)
        db.audit_log("rule_extract", patient_id=report_id, input_text=req.text[:200],
                      output_text=str(report.get("study_see",""))[:200], detail={"method":"fetal_template", "confidence": conf})
        return {"success": True, "report": report, "report_id": report_id, "method": "fetal_template"}

    # 策略1: 固定模板 + 数值填充
    report = match_and_fill(correct_ASR_text(req.text), req.exam_type)
    if report and report.get("_template_matched"):
        report = _wrap_hints_with_toggle(report)
        report_id = None
        if req.patient_id and req.patient_id.strip():
            try:
                pid = int(req.patient_id)
                r = db.report_create(pid, match_template(req.exam_type), req.text, _filter_checked(report))
                report_id = r["id"]
            except (ValueError, Exception):
                pass
        conf = _confidence_score(report)
        db.audit_log("rule_extract", patient_id=report_id, input_text=req.text[:200],
                      output_text=str(report.get("study_see",""))[:200], detail={"method":"regex_fill", "confidence": conf})
        return {"success": True, "report": report, "report_id": report_id, "method": "regex_fill"}

    # 策略2: LLM 自由生成 + 异常兜底
    rule_report = None
    try:
        rule_report = _rule_fallback(correct_ASR_text(req.text), req.exam_type, req.patient_id)
    except Exception:
        pass

    try:
        report = llm_structure(sanitized_text, req.exam_type)
        # 交叉校验
        if rule_report:
            report = _cross_validate(rule_report, report, req.text)
        db.audit_log("llm_structure", patient_id=None, input_text=sanitized_text[:200],
                      output_text=str(report.get("study_see",""))[:200], detail={"method":"llm_free"})
    except Exception:
        # LLM异常 → 规则库兜底
        report = rule_report or _rule_fallback(correct_ASR_text(req.text), req.exam_type, req.patient_id)
        db.audit_log("rule_fallback", patient_id=None, input_text=req.text[:200],
                      output_text=str(report.get("study_see",""))[:200], detail={"error":"llm_exception"})
        logging.warning("LLM调用失败，使用规则库兜底")

    report = _wrap_hints_with_toggle(report)
    report_id = None
    if req.patient_id and req.patient_id.strip():
        try:
            pid = int(req.patient_id)
            r = db.report_create(pid, match_template(req.exam_type), req.text, _filter_checked(report))
            report_id = r["id"]
        except (ValueError, Exception):
            pass

    return {"success": True, "report": report, "report_id": report_id, "method": report.get("_method", "llm_free")}

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
    """保存报告（只保存 checked=true 的内容）+ 操作留痕"""
    if not report: raise HTTPException(400, "报告数据为空")
    inner = report.get("report") if isinstance(report.get("report"), dict) else None
    data = inner if inner else report
    cleaned = _filter_checked(data)
    r = db.report_update(report_id, edited=cleaned, structured=cleaned)
    if not r: raise HTTPException(404, "报告不存在")
    db.audit_log("doctor_save", patient_id=r.get("patient_id"), input_text=str(data)[:200],
                  output_text="saved", detail={"report_id": report_id})
    return {"success": True, "report": r, "message": "报告已保存"}

@app.post("/api/reports/{report_id}/send")
async def send_report(report_id: int, report: dict = None):
    """发送报告到 PACS + 操作留痕"""
    inner = report.get("report") if isinstance(report, dict) and isinstance(report.get("report"), dict) else None
    data = inner if inner else report
    cleaned = _filter_checked(data) if data else None
    r = db.report_confirm(report_id, cleaned or {})
    if not r: raise HTTPException(404, "报告不存在")
    logging.info(f"[PACS] 发送报告 report_id={report_id} patient_id={r['patient_id']}")
    db.audit_log("pacs_send", patient_id=r.get("patient_id"), input_text=str(data)[:200],
                  output_text="sent", detail={"report_id": report_id})
    return {"success": True, "message": "报告已保存并发送至PACS（Mock）", "report_id": report_id}

@app.post("/api/reports/{report_id}/confirm")
async def confirm_report(report_id: int, edited: dict = None):
    r = db.report_confirm(report_id, edited or {})
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

# 禁止路径遍历的文件名白名单
_ALLOWED_STATIC = {"index.html"}

if frontend_dir.exists():
    @app.get("/")
    async def index():
        return FileResponse(frontend_dir / "index.html")

    @app.get("/{filename}")
    async def serve_static(filename: str):
        path = filename.split("/")[0].split("\\")[0]
        if path not in _ALLOWED_STATIC:
            raise HTTPException(404)
        fpath = frontend_dir / path
        if fpath.exists() and fpath.is_file():
            return FileResponse(fpath)
        raise HTTPException(404)

if __name__ == "__main__":
    import uvicorn
    # 自签名证书，解决浏览器 HTTPS 安全上下文要求（语音识别需要 HTTPS 或 localhost）
    ssl_keyfile = Path(__file__).parent / "key.pem"
    ssl_certfile = Path(__file__).parent / "cert.pem"
    if ssl_keyfile.exists() and ssl_certfile.exists():
        uvicorn.run("main:app", host="0.0.0.0", port=8700, reload=True,
                    ssl_keyfile=str(ssl_keyfile), ssl_certfile=str(ssl_certfile))
    else:
        uvicorn.run("main:app", host="0.0.0.0", port=8700, reload=True)
