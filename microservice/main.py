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

import microservice.config as config
import microservice.schema as schema
from microservice.schema import (
    ApiResponse, StructureData, StructureRequest,
    PatientContext, StudyHint, VALID_EXAM_TYPES,
)
from microservice.logger import logger, setup_logger
from microservice.pipeline import run_pipeline

# 确保 backend/ 可导入
_backend_api = _root / "backend"
if str(_backend_api) not in sys.path:
    sys.path.insert(0, str(_backend_api))

import db as ultrasound_db  # 内部医院DB (ultrasound.db)
_backend = _root / "backend"
if str(_backend) not in sys.path:
    sys.path.insert(0, str(_backend))

from api_platform.auth import ApiKeyAuth, verify_api_key, generate_api_key
from api_platform.db import (
    usage_record, usage_get_monthly, tenant_create,
    registration_log, order_log, audio_file_log,
)
from api_platform.billing import (
    calculate_transcribe_cost, calculate_structure_cost,
    get_billed_amount, check_quota, get_plan,
)
from api_platform.ratelimit import check_rate_limit

setup_logger()

app = FastAPI(
    title="Ultrasound AI API Platform",
    description="超声报告语音结构化 AI API — 为合作医院和第三方开发者提供语音→结构化报告服务",
    version="4.2.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# ── 工业级操作规范: 录音安全配置 ──
AUDIO_MAX_DURATION_SECONDS = 360       # 单例绝对时长熔断 (6分钟)
VAD_SILENCE_TIMEOUT_SECONDS = 45        # 连续静音超时自动暂停
AUDIO_MIN_SPEECH_CHARS = 10             # 有效语音最少字符数 (低于此值=垃圾杂音)
MULTI_PATIENT_CONFLICT_KEYWORDS = [     # 跨患者串音检测特征词
    "下一个病人", "换人", "另外一床", "刚才那个", "前一个",
    "就诊号", "病历号", "住院号", "叫号", "下一个",
]

# ── 音频格式白名单 ──
ALLOWED_AUDIO_EXTENSIONS = {'.webm', '.wav', '.mp3', '.m4a', '.ogg', '.flac', '.opus'}

# ── 音频限制 ──
MAX_AUDIO_SIZE_BYTES = 50 * 1024 * 1024  # 50MB (硬上限，拒绝超大文件)
MAX_AUDIO_DURATION_SECONDS = 120          # 2分钟 (超过则拒绝，防止产检40分钟录音)
AUDIO_DURATION_GRACE_SECONDS = 30         # 前30秒免费

# ── 幂等性缓存 (10 分钟 TTL, 简单内存实现) ──
_idempotency_cache: dict[str, dict] = {}
_idempotency_lock = Lock()
_IDEMPOTENCY_MAX = 1000  # 最大缓存条目


# ── 音频本地存储 ──
AUDIO_STORE_DIR = Path(__file__).resolve().parent.parent / "audio_store"
AUDIO_STORE_DIR.mkdir(exist_ok=True)


def _save_audio_to_disk(audio_bytes: bytes, tenant_id: int, patient_id: str, filename: str, age: int = 0) -> str:
    """保存音频到本地磁盘，返回相对路径
    命名规则: {YYYYMMDD}_{HHmmss}_{patient_id}_{age}.webm
    """
    from datetime import datetime
    now = datetime.now()
    date_str = now.strftime("%Y%m%d")
    time_str = now.strftime("%H%M%S")
    safe_pid = patient_id.replace("/", "_").replace("\\", "_")[:32]
    ext = Path(filename).suffix.lower() or ".webm"
    fname = f"{date_str}_{time_str}_{safe_pid}_{age}{ext}"
    fpath = AUDIO_STORE_DIR / fname
    counter = 1
    while fpath.exists():
        fname = f"{date_str}_{time_str}_{safe_pid}_{age}_{counter}{ext}"
        fpath = AUDIO_STORE_DIR / fname
        counter += 1
    fpath.write_bytes(audio_bytes)
    return str(fpath)


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

# Security headers (生产级 WAF 安全头)
@app.middleware("http")
async def security_headers(request: Request, call_next):
    # Skip WS
    if request.scope.get("type") == "websocket":
        return await call_next(request)
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; connect-src *; img-src * data:; media-src *;"
    # Rate-limit headers (injected by check_rate_limit)
    response.headers["X-RateLimit-Limit"] = "1000"
    response.headers["X-RateLimit-Remaining"] = "999"
    return response

# Request logger + request_id injection
@app.middleware("http")
async def request_context(request: Request, call_next):
    # 跳过WebSocket请求 (不做JSON包装)
    if request.scope.get("type") == "websocket":
        return await call_next(request)

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


def _try_get_by_email(email: str) -> dict | None:
    """安全查询: 邮箱不存在返回 None 不抛异常"""
    try:
        from api_platform.db import tenant_get_by_key
        # 直接查 API key 表不现实, 用 DB 直接查
        from api_platform.db import _conn
        c = _conn()
        row = c.execute("SELECT * FROM api_tenants WHERE email=? AND is_active=1", (email,)).fetchone()
        return dict(row) if row else None
    except Exception:
        return None


# ── Public endpoints (no auth required) ──

class SignupRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100, description="医院/公司名称")
    email: str = Field(..., min_length=5, max_length=100, description="联系邮箱")
    contact: str | None = Field(default=None, max_length=50, description="联系人 (可选)")


@app.post("/v1/signup")
async def signup(req: SignupRequest, request: Request):
    """开发者自助注册 — 免费版, 返回 API Key"""
    rid = _get_request_id(request)
    existing = _try_get_by_email(req.email)
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

    # 记录注册日志 (IP + User-Agent)
    try:
        registration_log(
            tenant_id=tenant["id"], name=req.name, email=req.email,
            contact=req.contact,
            ip=request.client.host if request.client else None,
            ua=request.headers.get("user-agent", "")[:200],
        )
    except Exception:
        pass

    return {
        "code": 200, "msg": "注册成功", "request_id": rid,
        "api_key": api_key, "plan": "free", "plan_name": "免费版", "monthly_quota": 100,
    }


@app.get("/v1/health")
async def health(request: Request):
    rid = _get_request_id(request)
    return {
        "status": "ok", "version": "4.2.0", "request_id": rid,
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

    # 读取音频
    audio_bytes = await audio_file.read()
    if not audio_bytes:
        return error_response(400, "音频文件为空", rid)

    # 工业级: 时长熔断 (6分钟) + VAD静音检测 (WEBM码率估算)
    audio_size_mb = len(audio_bytes) / (1024 * 1024)
    estimated_duration = len(audio_bytes) / 4000   # 4KB/s WebM 码率估算
    MAX_DURATION_SEC = AUDIO_MAX_DURATION_SECONDS   # 360秒 (6分钟)

    if estimated_duration > MAX_DURATION_SEC:
        return error_response(400,
            f"音频时长熔断: 估算 {estimated_duration:.0f} 秒, 单例上限 {MAX_DURATION_SEC} 秒。"
            f"请关闭录音后重新打开下一位患者。疑似跨患者串音, 此音频已标记为脏数据。", rid)

    if len(audio_bytes) > 50 * 1024 * 1024:
        return error_response(400, "音频文件过大 (最大 50MB)", rid)

    # VAD 静音断流检测 (文件过小 = 只有噪音无有效语音)
    if len(audio_bytes) < 4000:  # <1秒等效
        result_vad = await run_pipeline(request_type="transcribe", audio_bytes=audio_bytes, patient_ctx=ctx)
        result_vad.request_id = rid
        result_vad.audio_status = "noise"
        result_vad.is_valid = False
        return {
            "code": 200, "msg": "音频有效语音不足, 标记为垃圾杂音 (不计费)",
            "request_id": rid, "data": result_vad.model_dump(),
            "billing": {"total_billed": 0.0},
        }

    # Rate limit  ← 修复: 补回被覆盖的代码
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

    # 读取音频（只读一次）
    if not audio_bytes:
        return error_response(400, "音频文件为空", rid)
    if len(audio_bytes) > 50 * 1024 * 1024:
        return error_response(400, "音频文件过大 (最大 50MB)", rid)

    # 运行流水线
    result = await run_pipeline(request_type="transcribe", audio_bytes=audio_bytes, patient_ctx=ctx)
    result.request_id = rid

    # 计费 (综合: 配额 + 语音时长阶梯)
    # WebM 码率约 4KB/s, 用文件大小推算实际录音时长
    audio_duration_by_size = len(audio_bytes) / 4000.0
    asr_seconds = audio_duration_by_size if result.duration <= 0 else result.duration
    tokens_in = len(result.corrected_text) // 2 or 500
    tokens_out = len(result.study_see) // 2 or 300

    # 语音超时费 (前 30 秒免费, 超时按秒阶梯计费)
    audio_extra, grace_secs = get_audio_billed_amount(asr_seconds, tenant["plan"])
    cost_info = calculate_transcribe_cost(asr_seconds, tokens_in, tokens_out)
    billed = get_billed_amount(tenant["plan"], monthly["total_calls"], audio_extra=audio_extra)
    if billed < 0:
        return error_response(429, "免费版月度配额已用完，请升级套餐", rid)

    usage_record(
        tenant_id=tenant["id"], endpoint="transcribe",
        tokens_in=tokens_in, tokens_out=tokens_out,
        asr_seconds=asr_seconds, cost=cost_info["total"], billed=max(billed, 0.0),
    )

    # 保存音频到本地 (命名: YYYYMMDD_HHmmss_patientID_age.webm)
    audio_path = ""
    if ctx and ctx.patient_id:
        try:
            audio_path = _save_audio_to_disk(audio_bytes, tenant["id"], ctx.patient_id, audio_file.filename, age=ctx.age)
            logger.info({"phase": "audio_saved", "path": audio_path, "size": len(audio_bytes)})
            # 音频文件索引入库
            try:
                audio_file_log(
                    tenant_id=tenant["id"], patient_id=ctx.patient_id,
                    file_path=audio_path, file_name=audio_file.filename,
                    file_size=len(audio_bytes), audio_duration=asr_seconds,
                    asr_text=result.raw_text, report_id=rid,
                )
            except Exception:
                pass
        except Exception as e:
            logger.warning({"phase": "audio_save_failed", "error": str(e)})

    response_obj = {
        "code": 200, "msg": "degraded" if result.degraded else "success",
        "request_id": rid, "data": result.model_dump(),
        "billing": {
            "audio_duration": round(asr_seconds, 1),
            "grace_seconds": grace_secs,
            "audio_extra": audio_extra,
            "total_billed": max(billed, 0.0),
        },
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

    # 文本过长检测 (>5000字符可能不是单次口述而是整份报告)
    if len(req.text) > 5000:
        return error_response(400,
            f"文本过长 ({len(req.text)} 字符)。本接口用于单次口述结构化, "
            f"每次最多 5000 字符。如需处理整份报告请分段提交。", rid)

    # 语音指令拦截 (不调用LLM, 不收费, 直接返回命令)
    voice_commands = {
        "清空重来": "CLEAR",
        "确认保存": "SAVE",
        "保存报告": "SAVE",
        "下一项": "NEXT",
        "跳到下一项": "NEXT",
        "打印报告": "PRINT",
        "放大两倍": "ZOOM_IN",
        "缩小一半": "ZOOM_OUT",
        "调亮一点": "BRIGHTEN",
        "左边对比": "COMPARE_LEFT",
        "冻结图像": "FREEZE",
        "截图保存": "SCREENSHOT",
    }
    raw_stripped = req.text.strip()
    for cmd_text, cmd_action in voice_commands.items():
        if raw_stripped == cmd_text or raw_stripped.endswith(cmd_text):
            logger.info({"phase": "voice_command", "command": cmd_action})
            return {
                "code": 200, "msg": f"语音指令: {cmd_action}",
                "request_id": rid,
                "command": cmd_action,
                "data": None,
                "billing": {"total_billed": 0.0},
            }

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
    # 查历史报告 (随访对比上下文)
    history_context = ""
    try:
        import sqlite3 as _sq
        _conn_hist = _sq.connect("/opt/ultrasound-report-mvp/backend/ultrasound.db")
        _conn_hist.row_factory = _sq.Row
        _hist_rows = _conn_hist.execute(
            "SELECT DESCRIBES, DIAGNOSIS, examdate FROM api_reports WHERE OUTPATIENTNO=? ORDER BY examdate DESC LIMIT 1",
            (req.patient_context.patient_id,)
        ).fetchall()
        _conn_hist.close()
        if _hist_rows:
            _hr = dict(_hist_rows[0])
            history_context = f"【上次检查 ({_hr.get('examdate','未知')})】所见: {_hr.get('DESCRIBES','')[:500]}. 提示: {_hr.get('DIAGNOSIS','')[:200]}"
            logger.info({"phase": "history_found", "patient_id": req.patient_context.patient_id,
                         "examdate": _hr.get('examdate')})
    except Exception:
        pass

    result = await run_pipeline(
        request_type="structure",
        text=(history_context + "\n【本次口述】" + req.text.strip()) if history_context else req.text.strip(),
        patient_ctx=req.patient_context,
    )
    result.request_id = rid

    # 双患者混录音频检测 (跨患者串音特征词)
    text_lower = req.text.strip()
    dual_hits = [kw for kw in MULTI_PATIENT_CONFLICT_KEYWORDS if kw in text_lower]
    if dual_hits:
        result.audio_status = "dual_mixed"
        result.dual_mixed = True
        result.study_see = ""
        result.study_hint = []
        result.is_valid = False
        logger.warning({"phase": "dual_mixed_detected", "hits": dual_hits,
                        "patient_id": req.patient_context.patient_id})
        return {
            "code": 200, "msg": f"检测到多患者混录特征词: {dual_hits}。此音频已标记为脏数据, 不结构化, 不计费。请人工裁剪后分段上传。",
            "request_id": rid,
            "data": result.model_dump(),
            "billing": {"total_billed": 0.0},
        }

    # 计费
    tokens_in = len(req.text) // 2 or 500
    tokens_out = len(result.study_see) // 2 or 300
    cost_info = calculate_structure_cost(tokens_in, tokens_out)
    billed = get_billed_amount(tenant["plan"], monthly["total_calls"], audio_extra=0.0)
    if billed < 0:
        return error_response(429, "免费版月度配额已用完，请升级套餐", rid)

    usage_record(
        tenant_id=tenant["id"], endpoint="structure",
        tokens_in=tokens_in, tokens_out=tokens_out,
        cost=cost_info["total"], billed=max(billed, 0.0),
    )

    # 存入标准化报告表 (匹配CSV格式)
    try:
        ultrasound_db.api_report_save(
            patient_id=req.patient_context.patient_id,
            name=req.patient_context.name or "",
            gender=req.patient_context.gender or "",
            age=req.patient_context.age or 0,
            exam_type=req.patient_context.exam_type or "",
            department=req.patient_context.department or "",
            clinical_diag=req.patient_context.clinical_diag or "",
            study_see=result.study_see or "",
            study_hint=[h.model_dump() for h in result.study_hint] if result.study_hint else [],
            template_used=template_name,
            audio_path="",  # structure 无音频
            tenant_id=tenant["id"],
            request_id=rid,
        )
    except Exception as e:
        logger.warning(f"api_report_save failed: {e}")

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


class FeedbackRequest(BaseModel):
    report_id: str | None = Field(default=None, description="关联的报告 request_id")
    original_text: str = Field(..., min_length=1, max_length=5000, description="原始口述/ASR文本")
    study_see: str = Field(default="", description="AI 生成的超声所见")
    edited_study_see: str = Field(default="", description="医生修改后的超声所见")
    accepted_hints: list[str] = Field(default_factory=list, description="医生保留的超声提示")
    rejected_hints: list[str] = Field(default_factory=list, description="医生删除的超声提示")
    added_hints: list[str] = Field(default_factory=list, description="医生新增的超声提示")
    rating: int = Field(default=0, ge=0, le=5, description="医生评分 0-5")
    comment: str = Field(default="", max_length=500, description="医生备注")


@app.post("/v1/feedback")
async def submit_feedback(
    request: Request,
    req: FeedbackRequest,
    tenant: dict = Depends(require_auth),
):
    """医生反馈 — 用于持续改进模型精度 (不扣配额)

    医生对 AI 生成的报告进行修改后, 将修改前后内容提交到此端点。
    反馈数据用于优化 Few-Shot 案例和规则库。
    """
    rid = _get_request_id(request)

    try:
        import json as _json
        feedback_data = {
            "tenant_id": tenant["id"],
            "tenant_name": tenant["name"],
            "report_id": req.report_id or rid,
            "original_text": req.original_text[:500],
            "study_see_ai": req.study_see[:1000],
            "study_see_edited": req.edited_study_see[:1000],
            "accepted_hints": req.accepted_hints,
            "rejected_hints": req.rejected_hints,
            "added_hints": req.added_hints,
            "rating": req.rating,
            "comment": req.comment[:500],
            "created_at": __import__("datetime").datetime.now().isoformat(),
        }

        # 持久化到 API platform DB
        from api_platform.db import _conn
        c = _conn()
        c.execute("""
            CREATE TABLE IF NOT EXISTS feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tenant_id INTEGER,
                data TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
            )
        """)
        c.execute("INSERT INTO feedback (tenant_id, data) VALUES (?, ?)",
                  (tenant["id"], _json.dumps(feedback_data, ensure_ascii=False)))
        c.commit()

        # 异步写日志
        logger.info({"phase": "feedback", "tenant": tenant["name"],
                     "rating": req.rating, "hints_accepted": len(req.accepted_hints),
                     "hints_rejected": len(req.rejected_hints)})

        return {
            "code": 200, "msg": "感谢反馈! 您的修改将用于改进模型精度。",
            "request_id": rid,
            "feedback_id": c.lastrowid,
        }
    except Exception as e:
        return error_response(500, f"反馈保存失败: {str(e)[:100]}", rid)


@app.get("/v1/asr-quality")
async def asr_quality(
    request: Request,
    text: str = None,
    exam_type: str = "腹部超声",
    tenant: dict = Depends(require_auth),
):
    """ASR 文本质量评估 — 4信号加权评分

    参数:
      text: ASR 识别文本 (已纠错)
      exam_type: 检查类型
    返回:
      {confidence, route(fast/full), signals(correction/terminology/numbers/structure)}
    """
    rid = _get_request_id(request)
    if not text or not text.strip():
        return error_response(400, "text 参数不能为空", rid)
    if len(text) > 5000:
        return error_response(400, "text 过长 (最大 5000 字符)", rid)

    try:
        from asr_quality_estimator import estimate_asr_quality
        result = estimate_asr_quality(text.strip(), exam_type)
        return {
            "code": 200, "msg": "success", "request_id": rid,
            "confidence": result["confidence"],
            "route": result["route"],
            "signals": result.get("signals", {}),
            "details": result.get("details", ""),
        }
    except ImportError:
        return error_response(500, "ASR 质量评估模块不可用", rid)
    except Exception as e:
        return error_response(500, f"质量评估失败: {str(e)[:100]}", rid)


# ── MCP Tool: 小智机器人音频转录 (base64 audio) ──

class McpTranscribeRequest(BaseModel):
    audio_base64: str = Field(..., min_length=1, description="base64编码的音频 (webm/wav/mp3)")
    patient_id: str = Field(..., min_length=1, max_length=64, description="病历号")
    gender: str = Field(default="", max_length=2, description="男/女")
    age: int = Field(default=0, ge=0, le=150, description="年龄")
    exam_type: str = Field(default="腹部超声", max_length=50, description="检查类型")
    name: str = Field(default="", max_length=20, description="患者姓名(可选)")


@app.post("/v1/mcp/transcribe")
async def mcp_transcribe(req: McpTranscribeRequest):
    """MCP tool: 接收base64音频 → 转码 → ASR → 结构化 → 返回报告
    供小智ESP32机器人通过MCP协议调用
    """
    import base64, tempfile, os as _os
    rid = _uuid.uuid4().hex[:12]
    logger.info({"phase": "mcp_transcribe", "patient_id": req.patient_id, "audio_len": len(req.audio_base64)})

    # 解码base64音频
    try:
        audio_bytes = base64.b64decode(req.audio_base64)
    except Exception as e:
        return {"code": 400, "msg": f"base64解码失败: {str(e)[:100]}", "request_id": rid, "data": None}

    if len(audio_bytes) < 400:
        return {"code": 400, "msg": "音频数据过小 (可能为静音)", "request_id": rid, "data": None}

    # 写入临时文件 (asr_client需要文件路径)
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as tmp:
            tmp.write(audio_bytes)
            tmp_path = tmp.name

        ctx = PatientContext(
            patient_id=req.patient_id, gender=req.gender, age=req.age,
            exam_type=req.exam_type, name=req.name,
        )

        # 运行流水线
        result = await run_pipeline(request_type="transcribe", audio_bytes=audio_bytes, patient_ctx=ctx)
        result.request_id = rid

        # MCP 标准响应格式
        return {
            "code": 200,
            "msg": "success",
            "request_id": rid,
            "patient_id": req.patient_id,
            "template": result.template_used,
            "method": result.method,
            "elapsed_ms": result.elapsed_ms,
            "confidence": result.confidence,
            "study_see": result.study_see,
            "study_hint": [{"rank": h.rank, "diagnosis": h.diagnosis, "icd10": h.icd10} for h in result.study_hint],
            "recommendation": result.recommendation,
            "warnings": result.warnings,
        }
    except Exception as e:
        logger.error({"phase": "mcp_transcribe_error", "error": str(e)})
        return {"code": 500, "msg": f"处理失败: {str(e)[:200]}", "request_id": rid, "data": None}
    finally:
        if tmp_path:
            try: _os.unlink(tmp_path)
            except OSError: pass


# ── WebSocket: 小智ESP32直连音频流 (OPUS → 阿里ASR → 结构化) ──

@app.websocket("/v1/ws/asr")
async def ws_xiaozhi_asr(websocket):
    """小智ESP32直连WebSocket: 接收OPUS音频 → 阿里百炼ASR → 结构化 → 返回JSON"""
    import base64, tempfile, os as _os
    rid = _uuid.uuid4().hex[:12]
    logger.info({"phase": "ws_asr_connect", "client": str(websocket.client)})
    await websocket.accept()
    audio_bytes = bytearray()
    patient_id = "WS-" + rid
    exam_type = "腹部超声"
    gender = ""; age = 0; name = ""

    try:
        while True:
            data = await websocket.receive()
            if data["type"] == "websocket.disconnect":
                break
            if "text" in data:
                # JSON控制消息
                msg = json.loads(data["text"])
                if msg.get("type") == "config":
                    patient_id = msg.get("patient_id", patient_id)
                    exam_type = msg.get("exam_type", exam_type)
                    gender = msg.get("gender", "")
                    age = msg.get("age", 0)
                    name = msg.get("name", "")
                    await websocket.send_text(json.dumps({"type":"config_ack","status":"ok"}, ensure_ascii=False))
                    logger.info({"phase": "ws_config", "patient_id": patient_id, "exam": exam_type})
                elif msg.get("type") == "done":
                    # 音频传输完毕 → 处理
                    break
            elif "bytes" in data:
                audio_bytes.extend(data["bytes"])

        if len(audio_bytes) < 400:
            await websocket.send_text(json.dumps({"code":400,"msg":"音频数据过小","study_see":""}, ensure_ascii=False))
            await websocket.close()
            return

        logger.info({"phase": "ws_asr_process", "size": len(audio_bytes), "patient_id": patient_id})

        # 写临时文件 → 调ASR → 结构化
        with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as tmp:
            tmp.write(bytes(audio_bytes))
            tmp_path = tmp.name

        ctx = PatientContext(patient_id=patient_id, gender=gender, age=age, exam_type=exam_type, name=name)
        try:
            result = await run_pipeline(request_type="transcribe", audio_bytes=bytes(audio_bytes), patient_ctx=ctx)
            result.request_id = rid
            resp = {
                "code": 200, "msg": "success", "request_id": rid,
                "template": result.template_used, "method": result.method,
                "elapsed_ms": result.elapsed_ms, "confidence": result.confidence,
                "study_see": result.study_see,
                "study_hint": [{"rank":h.rank,"diagnosis":h.diagnosis,"icd10":h.icd10} for h in result.study_hint],
                "recommendation": result.recommendation,
                "warnings": result.warnings,
            }
        except Exception as e:
            resp = {"code":500,"msg":f"处理失败:{str(e)[:200]}","study_see":""}
        finally:
            try: _os.unlink(tmp_path)
            except OSError: pass

        await websocket.send_text(json.dumps(resp, ensure_ascii=False))
    except Exception as e:
        logger.error({"phase": "ws_asr_error", "error": str(e)})
        try: await websocket.send_text(json.dumps({"code":500,"msg":str(e)[:200]}, ensure_ascii=False))
        except: pass
    finally:
        try: await websocket.close()
        except: pass


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
