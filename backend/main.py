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
import asyncio
import logging
from datetime import datetime

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from pydantic import BaseModel, Field

try:
    from asr_client import transcribe_audio
    ASR_AVAILABLE = True
except (ImportError, ModuleNotFoundError):
    ASR_AVAILABLE = False
    def _asr_unavailable(*a, **kw): raise RuntimeError("ASR不可用")
    transcribe_audio = _asr_unavailable

from llm_client import structure_report as llm_structure
from templates import match_template, TEMPLATES
from template_filler import match_and_fill
from template_engine_v2 import match_and_fill_optimized, search_optimized as template_search_v2
from fixed_template_engine import process_with_fixed_template, TEMPLATE_TAGS, DEFAULT_TEMPLATES
from asr_correction import correct_ASR_text
from template_fetal import fill_fetal_template
from knowledge.loader import get_kb
import db

app = FastAPI(title="超声报告语音结构化", version="4.0.0.ABCDEF")

# API Platform — 管理后台路由
from api_platform.admin import router as admin_router
app.include_router(admin_router)

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
API_TOKEN = os.getenv("API_TOKEN", "")  # 生产环境设置环境变量
if API_TOKEN:
    @app.middleware("http")
    async def api_auth(request: Request, call_next):
        # 放行: 根路径、health、OpenAPI文档、静态文件
        path = request.url.path
        if path in ("/", "/api/health", "/docs", "/openapi.json") or path.startswith("/api/audio/"):
            return await call_next(request)
        # 检查 Authorization header
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            return JSONResponse({"detail": "未授权: 缺少API Token"}, status_code=401)
        token = auth[7:]
        if token != API_TOKEN:
            return JSONResponse({"detail": "未授权: Token无效"}, status_code=403)
        return await call_next(request)

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
    inpatient_id: str | None = None      # 住院号
    outpatient_id: str | None = None     # 门诊号
    department: str | None = None        # 申请科室
    clinical_diag: str | None = None     # 开单临床诊断

@app.post("/api/patients/quick-add")
async def patient_quick_add(req: PatientAddRequest):
    if not req.name.strip(): raise HTTPException(400, "姓名不能为空")
    if req.gender not in ("男","女","M","F"): raise HTTPException(400, "性别只能为 男 或 女")
    if req.age < 0 or req.age > 150: raise HTTPException(400, "年龄不合法(0-150)")
    if len(req.name.strip()) < 1: raise HTTPException(400, "姓名至少1个字符")
    if not req.exam_type.strip(): raise HTTPException(400, "检查类型不能为空")
    if len(req.exam_type.strip()) > 50: raise HTTPException(400, "检查类型过长(最多50字符)")
    patient = db.patient_add(req.name.strip(), req.gender, req.age, req.exam_type.strip(), req.exam_part)
    db.audit_log("patient_add", patient_id=patient["id"], input_text=f"{req.name},{req.gender},{req.age}",
                  output_text=f"patient_id={patient['id']}", detail={"exam_type": req.exam_type})
    return {"success": True, "patient": patient}

@app.get("/api/patients/queue")
async def patient_queue():
    return {"success": True, "patients": db.patient_queue()}

@app.put("/api/patients/{patient_id}/status")
async def patient_update_status(patient_id: int, status: str = "检查中"):
    p = db.patient_update_status(patient_id, status)
    if not p: raise HTTPException(404, "患者不存在")
    db.audit_log("patient_status", patient_id=patient_id, input_text=status, output_text="ok")
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

@app.get("/api/audio/{audio_id}/download")
async def audio_download(audio_id: str):
    """下载原始录音到本机"""
    matches = list(AUDIO_DIR.glob(f"{audio_id}.*"))
    if not matches: raise HTTPException(404, "音频文件不存在")
    fpath = matches[0]
    return FileResponse(
        fpath,
        media_type="application/octet-stream",
        filename=fpath.name,
        headers={"Content-Disposition": f"attachment; filename={fpath.name}"}
    )

# ==================== 语音转写 ====================

@app.post("/api/transcribe")
async def transcribe(file: UploadFile = File(...)):
    """上传音频，返回转写文本 + audio_id"""
    if not file.filename: raise HTTPException(400, "文件格式不识别")
    audio_bytes = await file.read()
    if len(audio_bytes) < 1024: raise HTTPException(400, "音频文件过小")
    if len(audio_bytes) > 50 * 1024 * 1024: raise HTTPException(400, "音频文件过大")

    # 备份: 文件名格式 YYYYMMDDHH0001 (.webm/.wav)
    suffix = Path(file.filename).suffix or ".wav"
    now = datetime.now()
    prefix = now.strftime("%Y%m%d%H")
    # 自动递增序号: 查找当天该小时已有的文件数, 补4位序号
    existing = sorted(AUDIO_DIR.glob(f"{prefix}*{suffix}"))
    seq = len(existing) + 1
    fname = f"{prefix}{seq:04d}{suffix}"
    backup_path = AUDIO_DIR / fname
    # 处理同序号冲突 (极罕见但保险)
    while backup_path.exists():
        seq += 1
        fname = f"{prefix}{seq:04d}{suffix}"
        backup_path = AUDIO_DIR / fname
    audio_id = fname.rsplit(".", 1)[0]
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
    # 意图预识别字段
    patient_name: str | None = None
    patient_gender: str | None = None
    patient_age: int | None = None
    clinical_diag: str | None = None
    department: str | None = None

def _wrap_hints_with_toggle(report: dict) -> dict:
    """给 study_hint 每条包裹 checked + id，并过滤非dict条目"""
    hints = report.get("study_hint", [])
    clean = []
    for i, h in enumerate(hints):
        if isinstance(h, str):
            clean.append({"rank": i+1, "diagnosis": h, "icd10": "", "id": f"h{i}", "checked": True})
        elif isinstance(h, dict):
            h["id"] = f"h{i}"
            h["checked"] = True
            clean.append(h)
    report["study_hint"] = clean
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
    """数据脱敏：移除姓名、住院号、门诊号等PII后传给LLM"""
    if not patient_id:
        return text
    try:
        import re
        pid = int(patient_id)
        p = db.patient_get(pid)
        if p:
            if p.get("name"):
                text = text.replace(p["name"], "[患者]")
            if p.get("inpatient_id"):
                text = text.replace(p["inpatient_id"], "[住院号]")
            if p.get("outpatient_id"):
                text = text.replace(p["outpatient_id"], "[门诊号]")
        # 通用手机号/身份证号正则脱敏（不计入patient表字段）
        text = re.sub(r'1[3-9]\d{9}', '[手机号]', text)
        text = re.sub(r'\d{6}(19|20)\d{2}(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])\d{3}[\dXx]', '[身份证号]', text)
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
    """ABCDEF流水线: A(ASR)→B(free LLM)∥C(regex)→D(B+regex)→E(template)→F(cross-validate)"""
    if not req.text or not req.text.strip(): raise HTTPException(400, "文本为空")
    if len(req.text) > 10000: raise HTTPException(400, "文本过长")

    # 规则引擎加载 (函数级导入避免循环依赖)
    from rule_engine import get_rule

    # 胎儿路径关键词 + 正常报告检测 (提前加载，避免 UnboundLocalError)
    fetal_kw = get_rule("pipeline.fetal_path.keywords", ["产科","胎儿","四维","排畸","孕","BPD","双顶径","股骨长","胎心"])

    sanitized_text = _sanitize_pii(req.text, req.patient_id)
    corrected_text = correct_ASR_text(req.text)
    A = corrected_text  # A路 = ASR纠错后原文
    warnings = []

    # 性别/妊娠冲突检测
    sex_conflict = detect_sex_conflict(A, req.patient_gender)
    if sex_conflict:
        warnings.append(sex_conflict)
        A = mask_conflict_organs(A, req.patient_gender)
    pregnancy_conflict = detect_pregnancy_conflict(A, req.exam_type, req.patient_gender)
    if pregnancy_conflict:
        warnings.append(pregnancy_conflict)

    # 胎儿快速通道 (使用上面已加载的 fetal_kw)
    is_fetal_text = any(kw in (req.exam_type + (A or "")[:80]) for kw in fetal_kw)
    if is_fetal_text and req.patient_gender != "男":
        report = fill_fetal_template(A)
        report = _wrap_hints_with_toggle(report)
        report_id = None
        if req.patient_id and req.patient_id.strip():
            try:
                pid = int(req.patient_id)
                r = db.report_create(pid, match_template(req.exam_type), req.text, _filter_checked(report))
                report_id = r["id"]
            except (ValueError, Exception):
                pass
        return {"success": True, "report": report, "report_id": report_id, "method": "fetal_template",
                "warnings": warnings, "template_used": "胎儿超声标准模板", "confidence": 0.9,
                "conflicts": [], "sources": {"A_asr": A[:500], "B_free_llm": None, "C_regex": None,
                "D_enhanced": None, "E_template": None}}

    # ===== ABCDEF 流水线 (v3优化: 正常报告快速通道 + EF合并) =====
    import asyncio
    from llm_client import generate_free_report, select_fill_and_validate
    from template_loader import search_candidates, get_template_by_name

    # 正常报告快速检测 + 胎儿路径 (规则引擎配置)
    norm_cfg = get_rule("validation.normal_report_detection", {})
    NORMAL_KW = norm_cfg.get("normal_kw", [])
    ABNORMAL_KW = norm_cfg.get("abnormal_kw", [])
    fast_path_types = get_rule("pipeline.fast_path.exam_types", ["腹部超声", "甲状腺超声", "乳腺超声"])

    def _is_normal_report(text: str) -> bool:
        has_abnormal = any(kw in text for kw in ABNORMAL_KW)
        has_normal = any(kw in text for kw in NORMAL_KW)
        return has_normal and not has_abnormal

    if _is_normal_report(A) and req.exam_type in fast_path_types:
        # 快速通道: 规则引擎直出，跳过全部LLM调用
        C = match_and_fill_optimized(A, req.exam_type,
            patient_sex=req.patient_gender or '', patient_age=req.patient_age or 0,
            clinical_diag=req.clinical_diag or '') if (req.patient_gender or req.patient_age) else match_and_fill(A, req.exam_type)
        if not C or not C.get("_template_matched"):
            fixed = process_with_fixed_template(A, "")
            C = {"study_see": fixed.get("filled_template", A), "study_hint": fixed.get("study_hint", []),
                 "_template_matched": fixed.get("template_used", "正常"), "_method": "fast_normal"}

        report = _wrap_hints_with_toggle(C)
        report_id = None; pid = None
        if req.patient_id and req.patient_id.strip():
            try:
                pid = int(req.patient_id)
                r = db.report_create(pid, match_template(req.exam_type), req.text, _filter_checked(report))
                report_id = r["id"]
            except (ValueError, Exception):
                pass
        db.audit_log("fast_normal", patient_id=pid, input_text=req.text[:200],
                      output_text=str(report.get("study_see",""))[:200],
                      detail={"method": C.get("_method", "fast_normal")})
        return {"success": True, "report": report, "report_id": report_id, "method": "fast_normal",
                "warnings": warnings, "template_used": C.get("_template_matched", "正常"), "confidence": 0.95,
                "conflicts": [], "sources": {"A_asr": A[:300], "C_regex": {"study_see": C.get("study_see","")[:300] if C else ""}}, "top3": [{"name": t["tpl_name"], "pct": t["confidence_pct"]} for t in candidates[:3]] if candidates else []}

    # B和C并行
    async def _route_b():
        try:
            return await asyncio.to_thread(generate_free_report, A, req.exam_type)
        except Exception as e:
            logging.warning(f"B exception: {e}")
            return None

    async def _route_c():
        r = match_and_fill_optimized(A, req.exam_type,
            patient_sex=req.patient_gender or '', patient_age=req.patient_age or 0,
            clinical_diag=req.clinical_diag or '') if (req.patient_gender or req.patient_age) else match_and_fill(A, req.exam_type)
        fixed = process_with_fixed_template(A, "")
        if r and r.get("_template_matched"):
            return r
        return {"study_see": fixed.get("filled_template", A), "study_hint": fixed.get("study_hint", []),
                "_template_matched": fixed.get("template_used", "rule_fallback"), "_method": "c_regex"}

    B, C = await asyncio.gather(_route_b(), _route_c())

    # D路: B结果 → 规则引擎再分析
    async def _route_d():
        if not B or not B.get("study_see"): return None
        B_text = _extract_plain_text(B.get("study_see", ""))
        if not B_text or len(B_text) < 5: return None
        r = match_and_fill_optimized(B_text, req.exam_type,
            patient_sex=req.patient_gender or '', patient_age=req.patient_age or 0,
            clinical_diag=req.clinical_diag or '') if (req.patient_gender or req.patient_age) else match_and_fill(B_text, req.exam_type)
        if r and r.get("_template_matched"):
            return r
        fixed = process_with_fixed_template(B_text, "")
        return {"study_see": fixed.get("filled_template", B_text), "study_hint": fixed.get("study_hint", []),
                "_template_matched": fixed.get("template_used", ""), "_method": "d_enhanced"}

    D = await _route_d()

    # EF合并: ABCD → 一次v4-flash完成模板选择+填充+交叉验证
    candidates = search_candidates(A, req.exam_type, limit=8)

    # 模板匹配质量判断: 候选最高分<50或候选为空 → 无合适模板, 使用B路自由生成
    best_score = candidates[0]["score"] if candidates else 0
    template_good_match = best_score >= 50

    if template_good_match:
        EF = await asyncio.to_thread(select_fill_and_validate, A, B, C, D, req.exam_type, candidates)
        EF["_method"] = "abcdef_v3"
    else:
        # 无合适模板 → 回退到B路自由生成 + C路规则引擎混合
        b_see = B.get("study_see", "") if B else ""
        c_see = C.get("study_see", "") if C else ""
        # 优先B路自由生成(内容完整), C路作为补充
        # B路即使较短, 也包含ASR原文的全部关键信息
        fallback_see = b_see if b_see else c_see
        EF = {
            "template_name": "自由生成(无匹配模板)",
            "filled_study_see_html": fallback_see or f"<div class='rpt-html'>{A}</div>",
            "study_hint": (B.get("study_hint", []) if B else []) or (C.get("study_hint", []) if C else []),
            "recommendation": (B.get("recommendation", "") if B else "") or (C.get("recommendation", "") if C else ""),
            "confidence": 0.5,
            "conflicts": [{"field": "模板匹配", "sources": {"candidates": len(candidates), "best_score": best_score}, "resolution": "无合适模板,使用自由生成"}],
            "reasoning": f"候选模板最高分数{best_score}<50, 回退到B/C路自由生成",
            "_method": "abcdef_v3_fallback",
        }

    # === 验证层: 固定文本完整性 + 内容溯源 + 医疗合规 ===
    import re as _re
    template_name = EF.get("template_name", "")
    filled_html = EF.get("filled_study_see_html", "")
    validation_issues = []

    # L2: 固定文本完整性
    if template_name:
        tpl = get_template_by_name(template_name)
        if tpl and tpl.get("info1"):
            from llm_client import _extract_plain_text as _ept
            tpl_clean = _ept(tpl["info1"])
            tpl_fixed = _re.sub(r'\[[^\]]+\]', '', tpl_clean)
            tpl_fixed = _re.sub(r'\b\d+\.?\d*\s*(?:mm|cm)?', '', tpl_fixed)
            tpl_fixed = _re.sub(r'___+', '', tpl_fixed)
            tpl_fixed = _re.sub(r'\s{2,}', ' ', tpl_fixed).strip()

            filled_noval = _re.sub(r'<[^>]+>', '', filled_html)
            filled_noval = _re.sub(r'\[[^\]]+\]', '', filled_noval)
            filled_noval = _re.sub(r'\b\d+\.?\d*\s*(?:mm|cm)?', '', filled_noval)
            filled_noval = _re.sub(r'___+', '', filled_noval)
            filled_noval = _re.sub(r'\s{2,}', ' ', filled_noval).strip()

            struct_words = _re.findall(r'[一-鿿]{3,}', tpl_fixed)
            missing = [w for w in struct_words[:20] if w not in filled_noval]
            if len(missing) > len(struct_words) * 0.3 and struct_words:
                validation_issues.append(f"L2: 模板固定文本缺失{len(missing)}/{len(struct_words)}个关键词")
                logging.warning(f"L2 fail: tpl={template_name} missing={missing[:5]}")

    # L4: 内容溯源
    if C and C.get("study_see") and filled_html:
        c_nums = set(_re.findall(r'\b(\d+\.?\d*)\s*(?:mm|cm)?', _extract_plain_text(C.get("study_see", ""))))
        filled_clean_val = _extract_plain_text(filled_html)
        f_nums = set(_re.findall(r'\b(\d+\.?\d*)\s*(?:mm|cm)?', filled_clean_val))
        if c_nums and f_nums:
            extra = f_nums - c_nums
            if len(extra) > 3:
                validation_issues.append(f"L4: 引入{len(extra)}个规则引擎未提取的数值")
            missing_nums = c_nums - f_nums
            if len(missing_nums) > 3:
                validation_issues.append(f"L4: 遗漏{len(missing_nums)}个规则引擎数值")

    # L5: 医疗合规 — 矛盾描述 (从规则引擎加载)
    contradictions = [(c["negative"], c["positive"]) for c in get_rule("validation.contradictions", [])]
    filled_clean_all = _extract_plain_text(filled_html)
    for neg_list, pos_list in contradictions:
        has_neg = any(kw in filled_clean_all for kw in neg_list)
        has_pos = any(kw in filled_clean_all for kw in pos_list)
        if has_neg and has_pos:
            validation_issues.append(f"L5: 矛盾描述 '{neg_list[0]}'+'{pos_list[0]}'")

    if validation_issues:
        logging.warning(f"验证问题: {validation_issues}")
        if any("L2" in v for v in validation_issues) and C and C.get("study_see"):
            EF["filled_study_see_html"] = C.get("study_see", filled_html)
            EF["study_hint"] = C.get("study_hint", EF.get("study_hint", []))
            EF["confidence"] = min(EF.get("confidence", 0.8), 0.6)
            EF["_method"] = "abcdef_v3_degraded_L2"

    # 构建最终report
    template_name = EF.get("template_name", "")
    report = {
        "study_see": EF.get("filled_study_see_html", ""),
        "study_hint": EF.get("study_hint", []),
        "recommendation": EF.get("recommendation", ""),
        "_template_matched": template_name,
        "_method": "abcdef_v3",
        "_confidence": EF.get("confidence", 0),
        "_conflicts": EF.get("conflicts", []),
        "_reasoning": EF.get("reasoning", ""),
    }
    report = _wrap_hints_with_toggle(report)

    # P0-3: 统一颜色标记 — 对所有非胎儿模板也应用 voice/unfill 标签
    if report.get("study_see"):
        import re as _re2
        see_html = report["study_see"]
        # 标记未填充的数值占位符 (___mm / __ / 未测)
        see_html = _re2.sub(
            r'(___?\s*(?:mm|cm|毫米|厘米)?|未测|__)',
            r'<i class="unfill">\1</i>', see_html
        )
        # 标记已填充的数值 (纯数字+单位)
        def _mark_voice(m):
            val = m.group(0)
            if '<' in val: return val  # already tagged
            return f'<b class="voice">{val}</b>'
        see_html = _re2.sub(r'\b\d+(?:\.\d+)?\s*(?:mm|cm|毫米|厘米|次/分|克|平方厘米|Wd|级)?', _mark_voice, see_html)
        report["study_see"] = see_html

    # 保存
    report_id = None; pid = None
    if req.patient_id and req.patient_id.strip():
        try:
            pid = int(req.patient_id)
            r = db.report_create(pid, match_template(req.exam_type), req.text, _filter_checked(report))
            report_id = r["id"]
        except (ValueError, Exception):
            pass

    db.audit_log("abcdef_v3", patient_id=pid, input_text=req.text[:200],
                  output_text=str(report.get("study_see",""))[:200],
                  detail={"template": template_name, "confidence": EF.get("confidence", 0)})

    import re as _re
    def _strip_html(s):
        return _re.sub(r'<[^>]+>', '', s or "").strip()

    return {
        "success": True, "report": report, "report_id": report_id,
        "method": "abcdef_v3", "warnings": warnings,
        "template_used": template_name,
        "confidence": EF.get("confidence", 0),
        "conflicts": EF.get("conflicts", []),
        "reasoning": EF.get("reasoning", ""),
        "sources": {
            "A_asr": A[:500],
            "B_free_llm": {"study_see": _strip_html(B.get("study_see",""))[:500], "study_hint": B.get("study_hint",[])} if B else None,
            "C_regex": {"study_see": _strip_html(C.get("study_see",""))[:500], "study_hint": C.get("study_hint",[])} if C else None,
            "D_enhanced": {"study_see": _strip_html(D.get("study_see",""))[:500], "study_hint": D.get("study_hint",[])} if D else None,
            "EF_combined": {"template_name": template_name, "filled": _strip_html(EF.get("filled_study_see_html",""))[:500]},
        },
    }


def _extract_plain_text(html_or_text: str) -> str:
    import re as _re
    text = _re.sub(r'<[^>]+>', '', html_or_text or "")
    text = _re.sub(r'\s+', ' ', text)
    return text.strip()


# ==================== 性别冲突检测 + 妊娠冲突检测 ====================
from rule_engine import get_rule

FEMALE_ONLY_ORGANS = set(get_rule("validation.sex_guard.female_only", []))
MALE_ONLY_ORGANS = set(get_rule("validation.sex_guard.male_only", []))
PREG_KW = get_rule("validation.contradictions", [])  # used in pregnancy detection below

def detect_sex_conflict(text: str, patient_gender: str | None) -> str | None:
    """检测性别冲突, 返回警告文本"""
    if not patient_gender: return None
    if patient_gender == "男":
        conflicts = [o for o in FEMALE_ONLY_ORGANS if o in text]
        if conflicts:
            return "性别冲突: 患者为男性, 但文本包含女性器官: " + "、".join(conflicts)
    elif patient_gender == "女":
        conflicts = [o for o in MALE_ONLY_ORGANS if o in text]
        if conflicts:
            return "性别冲突: 患者为女性, 但文本包含男性器官: " + "、".join(conflicts)
    return None

def mask_conflict_organs(text: str, patient_gender: str | None) -> str:
    """将冲突器官词替换为 [待确认]"""
    if not patient_gender: return text
    if patient_gender == "男":
        for o in FEMALE_ONLY_ORGANS:
            text = text.replace(o, "[待确认]")
    elif patient_gender == "女":
        for o in MALE_ONLY_ORGANS:
            text = text.replace(o, "[待确认]")
    return text

def detect_pregnancy_conflict(text: str, exam_type: str, patient_gender: str | None) -> str | None:
    """检测妊娠词汇与患者上下文的冲突"""
    preg_cfg = get_rule("validation", {}).get("pregnancy_guard", {})
    pregnancy_kw = set(preg_cfg.get("pregnancy_kw", ["孕囊","胎心","胎盘","羊水","脐带","早孕","中孕"]))
    found = [kw for kw in pregnancy_kw if kw in text]
    if not found: return None
    if patient_gender == "男":
        return "严重冲突: 男性患者文本含妊娠相关词汇: " + "、".join(found)
    if exam_type and "产" not in exam_type and "妇" not in exam_type and "孕" not in exam_type:
        return "注意: 非妇产检查中出现妊娠词汇: " + "、".join(found)
    return None

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
    r = db.report_update(report_id, edited=cleaned)
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

# ==================== 固定模板 + 意图识别 ====================

class FixedTemplateRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=10000)
    fixed_template: str = Field(default="", max_length=5000)

@app.post("/api/fixed-template/structure")
async def fixed_template_structure(req: FixedTemplateRequest):
    """
    一键意图识别 + 字段抽取 + 填入固定模板
    - 输入: ASR文本 + 可选固定模板
    - 输出: 填充后的模板 + 意图类别 + 标签列表
    """
    if not req.text or not req.text.strip():
        raise HTTPException(400, "文本为空")
    if len(req.text) > 10000:
        raise HTTPException(400, "文本过长")

    result = process_with_fixed_template(
        correct_ASR_text(req.text),
        req.fixed_template
    )
    return {"success": True, **result}

@app.get("/api/fixed-template/tags")
async def get_template_tags():
    """获取全部模板分类标签"""
    return {"success": True, "tags": TEMPLATE_TAGS}

@app.get("/api/fixed-template/defaults")
async def get_default_templates():
    """获取各类别的默认固定模板"""
    return {"success": True, "templates": DEFAULT_TEMPLATES}

# ==================== 静态文件 ====================

frontend_dir = Path(__file__).resolve().parent.parent / "frontend"

# 禁止路径遍历的文件名白名单
_ALLOWED_STATIC = {"index.html", "developer.html"}
docs_dir = Path(__file__).resolve().parent.parent / "docs"

if frontend_dir.exists():
    @app.get("/")
    async def index():
        return FileResponse(frontend_dir / "index.html")

    @app.get("/app")
    async def app_page():
        return FileResponse(docs_dir / "index.html") if (docs_dir / "index.html").exists() else Response(status_code=404)

    @app.get("/architecture")
    async def arch_page():
        return FileResponse(docs_dir / "architecture.html") if (docs_dir / "architecture.html").exists() else Response(status_code=404)

    @app.get("/mock-pacs")
    async def mock_pacs():
        return FileResponse(docs_dir / "mock_pacs.html") if (docs_dir / "mock_pacs.html").exists() else Response(status_code=404)

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
