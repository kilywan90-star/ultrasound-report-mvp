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

# === 新拆分路由模块 ===
from routers.fixed_template import router as fixed_template_router
from routers.audio import router as audio_router
from routers.quick_patients import router as quick_patients_router
from routers.main_reports import router as main_reports_router
from routers.structure import router as structure_router

# === main_v3 兼容路由（供前端复用）===
from routers.doctors import router as doctors_router
from routers.stats import router as stats_router
from routers.auto import router as auto_router
from routers.patients import router as mvp_patients_router
from routers.reports import router as mvp_reports_router
from routers.voice import router as mvp_voice_router

# main_v3 兼容路由需要 database.py 的表，确保初始化
from database import init_db as mvp_init_db
mvp_init_db()

import db

BUILD = "20260607-2103"
VERSION = f"v3.3.{BUILD}"

app = FastAPI(title="超声报告语音结构化", version=VERSION)

# === 注册路由 ===
app.include_router(section_templates_router)
app.include_router(pacs_router)
app.include_router(pacs_config_router)
app.include_router(syslog_router)
app.include_router(datalist_router)
app.include_router(exam_parts_router)

app.include_router(fixed_template_router)
app.include_router(audio_router)
app.include_router(quick_patients_router)
app.include_router(main_reports_router)
app.include_router(structure_router)

# === main_v3 兼容路由 ===
app.include_router(doctors_router)
app.include_router(stats_router)
app.include_router(auto_router)
app.include_router(mvp_patients_router)
app.include_router(mvp_reports_router)
app.include_router(mvp_voice_router)

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

@app.get("/api/templates")
async def list_templates():
    return {k: {"name": v["name"], "organs": v["organs"]} for k, v in TEMPLATES.items()}


# ==================== 静态文件 ====================

frontend_dir = Path(__file__).resolve().parent.parent / "frontend"

# 禁止路径遍历的文件名白名单
_ALLOWED_STATIC = {"index.html", "debug.html"}

if frontend_dir.exists():
    @app.get("/")
    async def index():
        return FileResponse(frontend_dir / "debug.html")

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
