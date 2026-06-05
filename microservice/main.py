"""
Ultrasound-AI-Service — FastAPI 微服务入口
独立服务, 端口 8800

端点:
  POST /api/v1/transcribe — 语音转录+结构化
  POST /api/v1/structure   — 纯文本结构化
  GET  /api/v1/health      — 健康检查
  GET  /api/v1/status      — 服务状态
"""

import sys, os, time, logging
from pathlib import Path

# 确保 backend/ 和 microservice/ 可导入
_root = Path(__file__).resolve().parents[1]
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from fastapi import FastAPI, File, HTTPException, Request, UploadFile, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from . import config
from .schema import (
    ApiResponse, StructureData, TranscribeRequest, StructureRequest,
    PatientContext, StudyHint,
)
from .logger import logger, setup_logger
from .pipeline import run_pipeline

# 确保 logger 初始化
setup_logger()

app = FastAPI(
    title="Ultrasound-AI-Service",
    description="超声报告语音结构化 AI 微服务",
    version="1.0.0",
    docs_url=None,      # 生产环境关闭 Swagger UI
    redoc_url=None,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "Authorization"],
)

# 安全中间件
@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    return response

# 请求日志
@app.middleware("http")
async def request_logger(request: Request, call_next):
    t0 = time.time()
    response = await call_next(request)
    elapsed = (time.time() - t0) * 1000
    logger.info({
        "method": request.method,
        "path": request.url.path,
        "status": response.status_code,
        "elapsed_ms": round(elapsed, 1),
    })
    return response

# 异常处理
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error({"error": str(exc), "path": str(request.url)})
    return JSONResponse(
        status_code=500,
        content=ApiResponse(
            code=500,
            msg=f"内部错误: {str(exc)[:200]}",
        ).model_dump(),
    )


# ── 端点 ──

@app.get("/api/v1/health")
async def health():
    """健康检查"""
    return {
        "status": "ok",
        "asr_available": config.ServiceStatus.asr_available,
        "llm_available": config.ServiceStatus.llm_available,
        "circuit_open": config.ServiceStatus.circuit_open,
        "total_requests": config.ServiceStatus.total_requests,
    }


@app.get("/api/v1/status")
async def status():
    """服务状态详情"""
    return {
        "total_requests": config.ServiceStatus.total_requests,
        "total_failures": config.ServiceStatus.total_failures,
        "total_degraded": config.ServiceStatus.total_degraded,
        "asr_available": config.ServiceStatus.asr_available,
        "llm_available": config.ServiceStatus.llm_available,
        "circuit_open": config.ServiceStatus.circuit_open,
    }


@app.post("/api/v1/transcribe")
async def transcribe(
    audio_file: UploadFile = File(...),
    patient_context: str = Form(default="{}"),
):
    """
    语音转录 + 结构化
    audio_file: 录音文件 (wav/mp3/webm)
    patient_context: JSON字符串 {"gender":"男","age":52,"exam_type":"腹部超声"}
    """
    if not audio_file.filename:
        return ApiResponse(code=400, msg="缺少音频文件").model_dump()

    # 解析 patient_context
    try:
        import json
        ctx_dict = json.loads(patient_context) if patient_context else {}
        ctx = PatientContext(**ctx_dict) if ctx_dict else None
    except Exception as e:
        logger.warning(f"patient_context 解析失败: {e}")
        ctx = None

    # 读取音频
    audio_bytes = await audio_file.read()
    if not audio_bytes:
        return ApiResponse(code=400, msg="音频文件为空").model_dump()

    # 运行流水线
    result = await run_pipeline(
        request_type="transcribe",
        audio_bytes=audio_bytes,
        patient_ctx=ctx,
    )

    return ApiResponse(
        code=200,
        msg="degraded" if result.degraded else "success",
        data=result,
    ).model_dump()


@app.post("/api/v1/structure")
async def structure(req: StructureRequest):
    """
    纯文本结构化 (无需音频)
    """
    if not req.text or not req.text.strip():
        return ApiResponse(code=400, msg="文本为空").model_dump()

    result = await run_pipeline(
        request_type="structure",
        text=req.text.strip(),
        patient_ctx=req.patient_context,
    )

    return ApiResponse(
        code=200,
        msg="degraded" if result.degraded else "success",
        data=result,
    ).model_dump()


# ── 启动 ──

if __name__ == "__main__":
    import uvicorn
    logger.info(f"Starting Ultrasound-AI-Service on {config.SERVICE_HOST}:{config.SERVICE_PORT}")
    uvicorn.run(
        "microservice.main:app",
        host=config.SERVICE_HOST,
        port=config.SERVICE_PORT,
        reload=config.DEBUG,
        log_level=config.LOG_LEVEL.lower(),
    )
