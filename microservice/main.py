"""
Ultrasound AI API Platform — 对外开放 API 网关 v4.1
端口 8800

端点:
  POST /v1/signup     — 自助注册 (免费, 不限流)
  POST /v1/transcribe — 语音转录+结构化 (核心, 计费)
  POST /v1/structure   — 纯文本结构化 (核心, 计费)
  GET  /v1/usage       — 查询租户用量
  GET  /v1/health      — 健康检查 (免费, 不限流)
  GET  /v1/status      — 服务状态 (免费, 不限流)

安全:
  - API Key: Authorization: Bearer sk-xxx
  - 请求去重: X-Idempotency-Key (可选, 10 分钟窗口)
  - 音频白名单: .webm, .wav, .mp3, .m4a, .ogg, .flac
  - 患者信息: patient_id/gender/age/exam_type 必传

响应格式 (统一信封):
  {"code": 200, "msg": "success", "request_id": "req_abc123", "data": {...}}
"""

import sys, os, time, logging, json, uuid as _uuid
from pathlib import Path
from threading import Lock

_root = Path(__file__).resolve().parents[1]
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from fastapi import FastAPI, File, HTTPException, Request, UploadFile, Form, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, ValidationError

from . import config
from .schema import (
    ApiResponse, StructureData, StructureRequest,
    PatientContext, StudyHint, VALID_EXAM_TYPES,
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
    version="4.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# ── 音频格式白名单 ──
ALLOWED_AUDIO_EXTENSIONS = {'.webm', '.wav', '.mp3', '.m4a', '.ogg', '.flac', '.opus'}

# ── 幂等性缓存 (10 分钟 TTL, 简单内存实现) ──
_idempotency_cache: dict[str, dict] = {}
_idempotency_lock = Lock()
_IDEMPOTENCY_MAX = 1000  # 最大缓存条目


def _get_request_id(request: Request) -> str:
    """从 header 或生成 request_id"""
    rid = request.headers.get("X-Request-ID", "")
    if not rid:
        rid = _uuid.uuid4().hex[:12]
    return rid


def _check_idempotency(key: str) -> dict | None:
    with _idempotency_lock:
        entry = _idempotency_cache.get(key)
        if entry and time.time() - entry["ts"] < 600:  # 10 分钟
            return entry["response"]
        # 清理过期条目
        if len(_idempotency_cache) > _IDEMPOTENCY_MAX:
            stale = [k for k, v in _idempotency_cache.items() if time.time() - v["ts"] > 600]
            for k in stale:
                del _idempotency_cache[k]
    return None


def _store_idempotency(key: str, response: dict):
    with _idempotency_lock:
        _idempotency_cache[key] = {"ts": time.time(), "response": response}


# ── 统一错误响应 ──
def error_response(code: int, msg: str, request_id: str = "", data: dict = None) -> dict:
    return {
        "code": code,
        "msg": msg,
        "request_id": request_id or _uuid.uuid4().hex[:12],
        "data": data,
    }


# ── Middleware ──

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "Authorization", "X-Request-ID", "X-Idempotency-Key"],
)

# Security headers
@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    return response

# Request logger + request_id injection
@app.middleware("http")
async def request_context(request: Request, call_next):
    t0 = time.time()
    rid = request.headers.get("X-Request-ID", "") or _uuid.uuid4().hex[:12]
    request.state.request_id = rid
    response = await call_next(request)
    elapsed = (time.time() - t0) * 1000
    # 确保所有响应都带 request_id
    try:
        body = b""
        async for chunk in response.body_iterator:
            body += chunk
        if response.status_code >= 200 and response.status_code < 300:
            try:
                data = json.loads(body)
                if isinstance(data, dict) and "request_id" not in data:
                    data["request_id"] = rid
                    body = json.dumps(data, ensure_ascii=False).encode()
            except (json.JSONDecodeError, UnicodeDecodeError):
                pass
        response = JSONResponse(
            content=json.loads(body) if body else {},
            status_code=response.status_code,
            headers=dict(response.headers),
        )
    except Exception:
        pass
    logger.info({
        "request_id": rid, "method": request.method, "path": request.url.path,
        "status": response.status_code, "elapsed_ms": round(elapsed, 1),
    })
    return response


# Validation error handler — 返回统一信封
@app.exception_handler(ValidationError)
async def validation_exception_handler(request: Request, exc: ValidationError):
    rid = getattr(request.state, "request_id", _uuid.uuid4().hex[:12])
    errors = exc.errors()
    detail = errors[0]["msg"] if errors else "请求参数校验失败"
    field = errors[0].get("loc", ["unknown"])[-1] if errors else "unknown"
    return JSONResponse(
        status_code=422,
        content=error_response(422, f"参数校验失败: {field} — {detail}", rid),
    )


# FastAPI HTTPException → 统一信封
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    rid = getattr(request.state, "request_id", _uuid.uuid4().hex[:12])
    return JSONResponse(
        status_code=exc.status_code,
        content=error_response(exc.status_code, exc.detail, rid),
    )


# Global fallback
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    import traceback
    rid = getattr(request.state, "request_id", _uuid.uuid4().hex[:12])
    body = None
    try:
        body = await request.body()
        body = body[:500]
    except Exception:
        pass
    logger.error({
        "request_id": rid, "error": str(exc), "path": str(request.url),
        "method": request.method, "content_type": request.headers.get("content-type", ""),
        "body_preview": body, "traceback": traceback.format_exc()[-500:],
    })
    return JSONResponse(
        status_code=500,
        content=error_response(500, f"内部错误: {str(exc)[:200]}", rid),
    )


# ── 辅助函数 ──

def _parse_patient_context(raw: str) -> PatientContext | None:
    """从 JSON 字符串解析并校验 PatientContext"""
    if not raw or raw == "{}":
        return None
    try:
        ctx_dict = json.loads(raw)
        return PatientContext(**ctx_dict)
    except (json.JSONDecodeError, Exception) as e:
        raise HTTPException(400, f"patient_context 解析失败: {str(e)[:100]}")


def _validate_audio_format(filename: str) -> None:
    """校验音频文件格式"""
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_AUDIO_EXTENSIONS:
        raise HTTPException(
            400,
            f"不支持的音频格式 '{ext}'。支持: {', '.join(sorted(ALLOWED_AUDIO_EXTENSIONS))}"
        )


# ── Public endpoints (no auth required) ──

class SignupRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100, description="医院/公司名称")
    email: str = Field(..., min_length=5, max_length=100, description="联系邮箱")
    contact: str | None = Field(default=None, max_length=50, description="联系人 (可选)")


@app.post("/v1/signup")
async def signup(req: SignupRequest, request: Request):
    """开发者自助注册 — 免费版, 返回 API Key"""
    rid = _get_request_id(request)
    existing = tenant_get_by_email(req.email)
    if existing:
        return {
            "code": 200, "msg": "该邮箱已注册，返回已有 API Key",
            "request_id": rid,
            "api_key": existing["api_key"], "plan": existing["plan"],
        }
    api_key = generate_api_key()
    tenant = tenant_create(
        name=req.name, plan="free",
        email=req.email, contact=req.contact,
        api_key=api_key,
    )
    return {
        "code": 200, "msg": "注册成功", "request_id": rid,
        "api_key": api_key, "plan": "free", "plan_name": "免费版", "monthly_quota": 100,
    }


@app.get("/v1/health")
async def health(request: Request):
    rid = _get_request_id(request)
    return {
        "status": "ok", "version": "4.1.0", "request_id": rid,
        "asr_available": config.ServiceStatus.asr_available,
        "llm_available": config.ServiceStatus.llm_available,
    }


@app.get("/v1/status")
async def status(request: Request):
    rid = _get_request_id(request)
    return {
        "request_id": rid,
        "total_requests": config.ServiceStatus.total_requests,
        "total_failures": config.ServiceStatus.total_failures,
        "total_degraded": config.ServiceStatus.total_degraded,
        "asr_available": config.ServiceStatus.asr_available,
        "llm_available": config.ServiceStatus.llm_available,
    }


# ── Authenticated endpoints ──

require_auth = ApiKeyAuth()


@app.post("/v1/transcribe")
async def transcribe(
    request: Request,
    audio_file: UploadFile = File(..., description="音频文件 (webm/wav/mp3/m4a/ogg/flac)"),
    patient_context: str = Form(..., min_length=5, description="患者上下文 JSON 字符串"),
    tenant: dict = Depends(require_auth),
    x_idempotency_key: str | None = Header(default=None, alias="X-Idempotency-Key"),
):
    """语音转录 + 结构化 (计费)

    - audio_file: 录音文件，最大 50MB
    - patient_context: JSON 字符串, 必传 patient_id/gender/age/exam_type

    示例 patient_context:
      {"patient_id":"MRN-20260606-001","gender":"男","age":52,"exam_type":"腹部超声"}
    """
    rid = _get_request_id(request)

    # 幂等性检查
    if x_idempotency_key:
        cached = _check_idempotency(x_idempotency_key)
        if cached:
            return cached

    # 音频文件校验
    if not audio_file.filename:
        return error_response(400, "缺少音频文件", rid)
    _validate_audio_format(audio_file.filename)

    # Rate limit
    allowed, rl_msg = check_rate_limit(tenant["id"], tenant["plan"], endpoint="transcribe")
    if not allowed:
        return error_response(429, rl_msg, rid)

    # Quota
    monthly = usage_get_monthly(tenant["id"])
    quota_ok, quota_msg = check_quota(tenant["plan"], monthly["total_calls"])
    if not quota_ok:
        return error_response(429, quota_msg, rid)

    # 解析并校验 patient_context
    try:
        ctx = _parse_patient_context(patient_context)
    except HTTPException as e:
        return error_response(e.status_code, e.detail, rid)

    # 读取音频
    audio_bytes = await audio_file.read()
    if not audio_bytes:
        return error_response(400, "音频文件为空", rid)
    if len(audio_bytes) > 50 * 1024 * 1024:
        return error_response(400, "音频文件过大 (最大 50MB)", rid)

    # 运行流水线
    result = await run_pipeline(request_type="transcribe", audio_bytes=audio_bytes, patient_ctx=ctx)
    result.request_id = rid

    # 计费
    asr_seconds = result.duration if result.duration > 0 else len(audio_bytes) / 16000.0
    tokens_in = len(result.corrected_text) // 2 or 500
    tokens_out = len(result.study_see) // 2 or 300
    cost_info = calculate_transcribe_cost(asr_seconds, tokens_in, tokens_out)
    billed = get_billed_amount(tenant["plan"], monthly["total_calls"], is_transcribe=True)
    if billed < 0:
        return error_response(429, "免费版月度配额已用完，请升级套餐", rid)

    usage_record(
        tenant_id=tenant["id"], endpoint="transcribe",
        tokens_in=tokens_in, tokens_out=tokens_out,
        asr_seconds=asr_seconds, cost=cost_info["total"], billed=max(billed, 0.0),
    )

    response_obj = {
        "code": 200, "msg": "degraded" if result.degraded else "success",
        "request_id": rid, "data": result.model_dump(),
    }

    if x_idempotency_key:
        _store_idempotency(x_idempotency_key, response_obj)

    return response_obj


@app.post("/v1/structure")
async def structure(
    request: Request,
    req: StructureRequest,
    tenant: dict = Depends(require_auth),
    x_idempotency_key: str | None = Header(default=None, alias="X-Idempotency-Key"),
):
    """纯文本结构化 (计费)

    请求体:
      {"text": "肝脏大小形态正常...", "patient_context": {"patient_id":"...","gender":"男","age":45,"exam_type":"腹部超声"}}
    """
    rid = _get_request_id(request)

    # 幂等性检查
    if x_idempotency_key:
        cached = _check_idempotency(x_idempotency_key)
        if cached:
            return cached

    # 文本校验
    if not req.text or not req.text.strip():
        return error_response(400, "text 字段不能为空", rid)
    if len(req.text) > 10000:
        return error_response(400, "text 字段过长 (最大 10000 字符)", rid)

    # Rate limit
    allowed, rl_msg = check_rate_limit(tenant["id"], tenant["plan"], endpoint="structure")
    if not allowed:
        return error_response(429, rl_msg, rid)

    # Quota
    monthly = usage_get_monthly(tenant["id"])
    quota_ok, quota_msg = check_quota(tenant["plan"], monthly["total_calls"])
    if not quota_ok:
        return error_response(429, quota_msg, rid)

    # 运行流水线
    result = await run_pipeline(
        request_type="structure",
        text=req.text.strip(),
        patient_ctx=req.patient_context,
    )
    result.request_id = rid

    # 计费
    tokens_in = len(req.text) // 2 or 500
    tokens_out = len(result.study_see) // 2 or 300
    cost_info = calculate_structure_cost(tokens_in, tokens_out)
    billed = get_billed_amount(tenant["plan"], monthly["total_calls"], is_transcribe=False)
    if billed < 0:
        return error_response(429, "免费版月度配额已用完，请升级套餐", rid)

    usage_record(
        tenant_id=tenant["id"], endpoint="structure",
        tokens_in=tokens_in, tokens_out=tokens_out,
        cost=cost_info["total"], billed=max(billed, 0.0),
    )

    response_obj = {
        "code": 200, "msg": "degraded" if result.degraded else "success",
        "request_id": rid, "data": result.model_dump(),
    }

    if x_idempotency_key:
        _store_idempotency(x_idempotency_key, response_obj)

    return response_obj


@app.get("/v1/usage")
async def my_usage(request: Request, tenant: dict = Depends(require_auth)):
    """查询当前租户的月度用量"""
    rid = _get_request_id(request)
    monthly = usage_get_monthly(tenant["id"])
    plan_info = get_plan(tenant["plan"])

    return {
        "code": 200, "msg": "success", "request_id": rid,
        "tenant": {
            "name": tenant["name"], "plan": tenant["plan"],
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
    logger.info(f"Starting Ultrasound AI API Platform v4.1 on {config.SERVICE_HOST}:{config.SERVICE_PORT}")
    uvicorn.run(
        "microservice.main:app",
        host=config.SERVICE_HOST,
        port=config.SERVICE_PORT,
        reload=config.DEBUG,
        log_level=config.LOG_LEVEL.lower(),
    )
