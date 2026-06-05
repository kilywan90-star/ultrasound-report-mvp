"""
Ultrasound AI API Platform — 对外开放 API 网关
端口 8800

端点:
  POST /v1/transcribe — 语音转录+结构化 (核心, 计费)
  POST /v1/structure   — 纯文本结构化 (核心, 计费)
  GET  /v1/usage       — 查询当前租户用量
  GET  /v1/health      — 健康检查 (免费, 不鉴权)
  GET  /v1/status      — 服务状态 (免费, 不鉴权)
"""

import sys, os, time, logging, json
from pathlib import Path

_root = Path(__file__).resolve().parents[1]
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from fastapi import FastAPI, File, HTTPException, Request, UploadFile, Form, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from . import config
from .schema import (
    ApiResponse, StructureData, TranscribeRequest, StructureRequest,
    PatientContext, StudyHint,
)
from .logger import logger, setup_logger
from .pipeline import run_pipeline

# API Platform imports
_backend = _root / "backend"
if str(_backend) not in sys.path:
    sys.path.insert(0, str(_backend))

from api_platform.auth import ApiKeyAuth, verify_api_key, generate_api_key
from api_platform.db import usage_record, usage_get_monthly, tenant_create, tenant_get_by_key as tenant_get_by_email
from api_platform.billing import (
    calculate_transcribe_cost, calculate_structure_cost,
    get_billed_amount, check_quota, get_plan,
)
from api_platform.ratelimit import check_rate_limit

setup_logger()

app = FastAPI(
    title="Ultrasound AI API Platform",
    description="超声报告语音结构化 AI API — 为合作医院和第三方开发者提供语音→结构化报告服务",
    version="4.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "Authorization"],
)

# Security headers
@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    return response

# Request logger
@app.middleware("http")
async def request_logger(request: Request, call_next):
    t0 = time.time()
    response = await call_next(request)
    elapsed = (time.time() - t0) * 1000
    logger.info({
        "method": request.method, "path": request.url.path,
        "status": response.status_code, "elapsed_ms": round(elapsed, 1),
    })
    return response

# Global exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    import traceback
    body = None
    try:
        body = await request.body()
        body = body[:500]
    except Exception:
        pass
    logger.error({
        "error": str(exc),
        "path": str(request.url),
        "method": request.method,
        "content_type": request.headers.get("content-type", ""),
        "body": body,
        "traceback": traceback.format_exc()[-500:],
    })
    return JSONResponse(
        status_code=500,
        content=ApiResponse(code=500, msg=f"内部错误: {str(exc)[:200]}").model_dump(),
    )


# ── Public endpoints (no auth required) ──


class SignupRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    email: str = Field(..., min_length=5, max_length=100)
    contact: str | None = None


@app.post("/v1/signup")
async def signup(req: SignupRequest):
    """开发者自助注册 — 免费版, 返回 API Key"""
    existing = tenant_get_by_email(req.email)
    if existing:
        return {
            "code": 200,
            "msg": "该邮箱已注册, 返回已有 API Key",
            "api_key": existing["api_key"],
            "plan": existing["plan"],
        }
    api_key = generate_api_key()
    tenant = tenant_create(
        name=req.name, plan="free",
        email=req.email, contact=req.contact,
        api_key=api_key,
    )
    return {
        "code": 200,
        "msg": "注册成功",
        "api_key": api_key,
        "plan": "free",
        "plan_name": "免费版",
        "monthly_quota": 100,
    }


@app.get("/v1/health")
async def health():
    return {
        "status": "ok",
        "version": "4.0.0",
        "asr_available": config.ServiceStatus.asr_available,
        "llm_available": config.ServiceStatus.llm_available,
    }


@app.get("/v1/status")
async def status():
    return {
        "total_requests": config.ServiceStatus.total_requests,
        "total_failures": config.ServiceStatus.total_failures,
        "total_degraded": config.ServiceStatus.total_degraded,
        "asr_available": config.ServiceStatus.asr_available,
        "llm_available": config.ServiceStatus.llm_available,
    }


# ── Authenticated endpoints (API Key required) ──

require_auth = ApiKeyAuth()


@app.post("/v1/transcribe")
async def transcribe(
    request: Request,
    audio_file: UploadFile = File(...),
    patient_context: str = Form(default="{}"),
    tenant: dict = Depends(require_auth),
):
    """语音转录 + 结构化 (计费)"""
    if not audio_file.filename:
        return ApiResponse(code=400, msg="缺少音频文件").model_dump()

    # Rate limit check
    allowed, rl_msg = check_rate_limit(tenant["id"], tenant["plan"], endpoint="transcribe")
    if not allowed:
        return ApiResponse(code=429, msg=rl_msg).model_dump()

    # Quota check
    monthly = usage_get_monthly(tenant["id"])
    quota_ok, quota_msg = check_quota(tenant["plan"], monthly["total_calls"])
    if not quota_ok:
        return ApiResponse(code=429, msg=quota_msg).model_dump()

    # Parse patient_context
    try:
        ctx_dict = json.loads(patient_context) if patient_context else {}
        ctx = PatientContext(**ctx_dict) if ctx_dict else None
    except Exception as e:
        logger.warning(f"patient_context parse error: {e}")
        ctx = None

    # Read audio
    audio_bytes = await audio_file.read()
    if not audio_bytes:
        return ApiResponse(code=400, msg="音频文件为空").model_dump()

    # Run pipeline
    result = await run_pipeline(
        request_type="transcribe",
        audio_bytes=audio_bytes,
        patient_ctx=ctx,
    )

    # Calculate costs
    asr_seconds = result.duration if result.duration > 0 else len(audio_bytes) / 16000.0
    tokens_in = len(result.corrected_text) // 2 or 500
    tokens_out = len(result.study_see) // 2 or 300
    cost_info = calculate_transcribe_cost(asr_seconds, tokens_in, tokens_out)
    billed = get_billed_amount(tenant["plan"], monthly["total_calls"], is_transcribe=True)
    if billed < 0:
        return ApiResponse(code=429, msg="免费版月度配额已用完, 请升级套餐").model_dump()

    # Record usage
    usage_record(
        tenant_id=tenant["id"], endpoint="transcribe",
        tokens_in=tokens_in, tokens_out=tokens_out,
        asr_seconds=asr_seconds,
        cost=cost_info["total"], billed=max(billed, 0.0),
    )

    return ApiResponse(
        code=200,
        msg="degraded" if result.degraded else "success",
        data=result,
    ).model_dump()


@app.post("/v1/structure")
async def structure(
    request: Request,
    req: StructureRequest,
    tenant: dict = Depends(require_auth),
):
    """纯文本结构化 (计费)"""
    if not req.text or not req.text.strip():
        return ApiResponse(code=400, msg="文本为空").model_dump()

    # Rate limit check
    allowed, rl_msg = check_rate_limit(tenant["id"], tenant["plan"], endpoint="structure")
    if not allowed:
        return ApiResponse(code=429, msg=rl_msg).model_dump()

    # Quota check
    monthly = usage_get_monthly(tenant["id"])
    quota_ok, quota_msg = check_quota(tenant["plan"], monthly["total_calls"])
    if not quota_ok:
        return ApiResponse(code=429, msg=quota_msg).model_dump()

    # Run pipeline
    result = await run_pipeline(
        request_type="structure",
        text=req.text.strip(),
        patient_ctx=req.patient_context,
    )

    # Calculate costs
    tokens_in = len(req.text) // 2 or 500
    tokens_out = len(result.study_see) // 2 or 300
    cost_info = calculate_structure_cost(tokens_in, tokens_out)
    billed = get_billed_amount(tenant["plan"], monthly["total_calls"], is_transcribe=False)
    if billed < 0:
        return ApiResponse(code=429, msg="免费版月度配额已用完, 请升级套餐").model_dump()

    # Record usage
    usage_record(
        tenant_id=tenant["id"], endpoint="structure",
        tokens_in=tokens_in, tokens_out=tokens_out,
        cost=cost_info["total"], billed=max(billed, 0.0),
    )

    return ApiResponse(
        code=200,
        msg="degraded" if result.degraded else "success",
        data=result,
    ).model_dump()


@app.get("/v1/usage")
async def my_usage(tenant: dict = Depends(require_auth)):
    """查询当前租户的月度用量"""
    monthly = usage_get_monthly(tenant["id"])
    plan_info = get_plan(tenant["plan"])

    return {
        "code": 200,
        "tenant": {
            "name": tenant["name"],
            "plan": tenant["plan"],
            "plan_name": plan_info["name"],
        },
        "usage": {
            "period": monthly["period"],
            "total_calls": monthly["total_calls"],
            "monthly_quota": plan_info["monthly_quota"],
            "remaining": max(0, plan_info["monthly_quota"] - monthly["total_calls"]),
            "total_tokens_in": monthly["total_tokens_in"],
            "total_tokens_out": monthly["total_tokens_out"],
            "total_asr_seconds": round(monthly["total_asr_seconds"], 1),
            "total_cost": round(monthly["total_cost"], 4),
            "total_billed": round(monthly["total_billed"], 2),
        },
    }


# ── Startup ──

if __name__ == "__main__":
    import uvicorn
    logger.info(f"Starting Ultrasound AI API Platform on {config.SERVICE_HOST}:{config.SERVICE_PORT}")
    uvicorn.run(
        "microservice.main:app",
        host=config.SERVICE_HOST,
        port=config.SERVICE_PORT,
        reload=config.DEBUG,
        log_level=config.LOG_LEVEL.lower(),
    )
