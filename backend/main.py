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
import re
import hmac
import json
import logging
from datetime import datetime

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

try:
    from asr_client import transcribe_audio
    ASR_AVAILABLE = True
except (ImportError, ModuleNotFoundError):
    ASR_AVAILABLE = False
    def _asr_unavailable(*a, **kw): raise RuntimeError("ASR不可用")
    transcribe_audio = _asr_unavailable

from templates import match_template, TEMPLATES
from api_section_templates import router as section_templates_router
from api_pacs import router as pacs_router
from api_pacs_config import router as pacs_config_router
from api_system_log import router as syslog_router
from api_data_list import router as datalist_router
from api_exam_parts import router as exam_parts_router

# === 主路由模块 ===
from routers.fixed_template import router as fixed_template_router
from routers.audio import router as audio_router
from routers.structure import router as structure_router

# main_v3 兼容路由需要 database.py 的表，确保初始化
from database import init_db as mvp_init_db
mvp_init_db()

import db

# ===== 初始化自动管线（必须在 import auto_router 之前）=====
from engine import Matcher
from pipeline import init_pipeline
_rulebase = Path(__file__).resolve().parent / "knowledge" / "超声规则库_rulebase.json"
if _rulebase.exists():
    with open(_rulebase, "r", encoding="utf-8") as _f:
        _rb = json.load(_f)
    _matcher = Matcher(_rb)
    init_pipeline(_matcher)
    print("[pipeline] 自动管线初始化成功")
else:
    print(f"[pipeline] 规则库不存在: {_rulebase}")

# === main_v3 兼容路由（供前端复用）=== 此时 pipeline 已就绪
from routers.doctors import router as doctors_router
from routers.stats import router as stats_router
from routers.auto import router as auto_router
from routers.patients import router as mvp_patients_router  # 已合并 quick_patients
from routers.reports import router as mvp_reports_router    # 已合并 main_reports
from routers.voice import router as mvp_voice_router
from routers.asr import router as unified_asr_router
from routers.audio_records import router as audio_records_router
from routers.workstation import router as workstation_router
from routers.asr_stream import router as asr_stream_router

BUILD = "20260607-2103"
VERSION = f"v3.3.{BUILD}"

app = FastAPI(title="超声报告语音结构化", version=VERSION)

# === 主路由注册 ===
app.include_router(section_templates_router)
app.include_router(pacs_router)
app.include_router(pacs_config_router)
app.include_router(syslog_router)
app.include_router(datalist_router)
app.include_router(exam_parts_router)

app.include_router(fixed_template_router)
app.include_router(audio_router)
app.include_router(structure_router)

# === v3 兼容路由（合并版）===
app.include_router(doctors_router)
app.include_router(stats_router)
app.include_router(auto_router)
app.include_router(mvp_patients_router)  # 含 CRUD + quick-add + queue
app.include_router(mvp_reports_router)    # 含 CRUD + save/send/confirm
app.include_router(mvp_voice_router)
app.include_router(unified_asr_router)
app.include_router(asr_stream_router)
app.include_router(audio_records_router)
app.include_router(workstation_router)

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

# API认证中间件 (基于Token)
API_TOKEN = os.getenv("API_TOKEN", "")
if API_TOKEN:
    @app.middleware("http")
    async def api_auth(request: Request, call_next):
        path = request.url.path
        if path in ("/", "/api/health", "/docs", "/openapi.json"):
            return await call_next(request)
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            return JSONResponse({"detail": "未授权: 缺少API Token"}, status_code=401)
        token = auth[7:]
        if not hmac.compare_digest(token, API_TOKEN):
            return JSONResponse({"detail": "未授权: Token无效"}, status_code=403)
        return await call_next(request)

# ==================== 通用 ====================

@app.get("/api/health")
async def health():
    from asr_client import _load_hotwords
    hw_count = len(_load_hotwords())
    return {"status": "ok", "version": VERSION, "build": BUILD,
            "templates": 70, "asr_hotwords": hw_count}

# ==================== 外部系统数据对接 ====================

@app.get("/api/external/reports")
def external_reports(since: str = "", limit: int = 100):
    """供外部系统拉取报告数据（直接读 api_reports 表）"""
    import db as _db
    c = _db._conn()
    if since:
        rows = c.execute(
            "SELECT * FROM api_reports WHERE created_at >= ? ORDER BY id DESC LIMIT ?",
            (since, limit)
        ).fetchall()
    else:
        rows = c.execute(
            "SELECT * FROM api_reports ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
    return {"reports": [dict(r) for r in rows], "total": len(rows)}


# ==================== 文件上传ASR (阿里云实时语音识别) ====================

@app.post("/api/asr/upload")
async def asr_upload(body: dict):
    """上传音频文件, 用阿里云百炼实时ASR识别"""
    import base64, tempfile, os, time, json, dashscope
    from pydantic import BaseModel

    audio_b64 = body.get("audio", "")
    audio_format = body.get("format", "wav")
    if not audio_b64:
        raise HTTPException(400, "音频数据为空")

    # base64解码
    try:
        audio_bytes = base64.b64decode(audio_b64)
    except Exception:
        raise HTTPException(400, "Base64解码失败")

    # 保存临时文件
    suffix = f".{audio_format}" if audio_format else ".wav"
    tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    tmp.write(audio_bytes)
    tmp_path = tmp.name
    tmp.close()

    # 阿里云ASR识别
    try:
        dashscope.api_key = os.getenv("DASHSCOPE_API_KEY") or "sk-6e6dfb5313964b2eb79bc72edf72b7db"
        import dashscope.audio.asr as asr_module

        # 上传文件
        upload = dashscope.Files.upload(file_path=tmp_path, purpose="file_trans")
        if upload.status_code != 200:
            return await _asr_whisper_fallback(audio_bytes, tmp_path)

        file_id = upload.output["uploaded_files"][0]["file_id"]
        file_info = dashscope.Files.get(file_id)
        file_url = file_info.output.get("url", "")

        if not file_url:
            return await _asr_whisper_fallback(audio_bytes, tmp_path)

        # 提交转写
        from dashscope.audio.asr import Transcription
        task = Transcription.async_call(model="qwen3-asr-flash-filetrans", file_urls=[file_url])
        if task.status_code != 200:
            text = await _asr_whisper_fallback_raw(audio_bytes, tmp_path)
            return {"text": text, "source": "whisper"}

        task_id = task.output["task_id"]
        for _ in range(120):
            r = Transcription.wait(task_id)
            s = r.output.get("task_status", "")
            if s == "SUCCEEDED":
                sentences = r.output.get("sentences", [])
                text = "".join([s.get("text", "") for s in sentences])
                os.unlink(tmp_path)
                return {"text": text, "source": "aliyun"}
            elif s == "FAILED":
                break
            time.sleep(1)

        # 失败降级到 Whisper
        text = await _asr_whisper_fallback_raw(audio_bytes, tmp_path)
        os.unlink(tmp_path)
        return {"text": text, "source": "whisper"}

    except Exception as e:
        text = await _asr_whisper_fallback_raw(audio_bytes, tmp_path)
        os.unlink(tmp_path)
        return {"text": text, "source": "whisper"}


async def _asr_whisper_fallback_raw(audio_bytes, tmp_path):
    """Whisper 兜底识别"""
    try:
        import whisper
        model = whisper.load_model("tiny")
        result = model.transcribe(tmp_path, language="zh")
        return result.get("text", "").strip()
    except Exception:
        return ""


@app.post("/api/asr/ali-realtime")
async def asr_ali_realtime(body: dict):
    """阿里云百炼实时语音识别 (websocket方式)"""
    import base64, os, time, json, dashscope
    audio_b64 = body.get("audio", "")
    if not audio_b64:
        raise HTTPException(400, "音频数据为空")

    # 阿里云实时ASR目前不支持单次POST, 需要WebSocket
    # 这里先用文件上传方式
    return await asr_upload(body)

@app.get("/api/templates")
async def list_templates():
    return {k: {"name": v["name"], "organs": v["organs"]} for k, v in TEMPLATES.items()}


# ==================== 静态文件 ====================

frontend_dir = Path(__file__).resolve().parent.parent / "frontend"

# 禁止路径遍历的文件名白名单
_ALLOWED_STATIC = {
    "index.html", "debug.html", "admin.html", "dashboard.html", "developer.html",
    "plans.html", "smart.html", "trace_logs.html", "error_report.html", "tablet.html", "director.html", "pad.html",
    "style.css", "api.js", "ui.js", "app.js", "tablet.js", "director.js", "pad.js",
}

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
    import os, uvicorn
    # 生产环境: workers=4 (通过环境变量 WORKERS=4 控制)
    # 开发环境: 默认 reload+单worker
    _workers = int(os.getenv("WORKERS", "1"))
    if _workers > 1:
        uvicorn.run("main:app", host="0.0.0.0", port=8700, workers=_workers)
    else:
        uvicorn.run("main:app", host="0.0.0.0", port=8700, reload=True)
