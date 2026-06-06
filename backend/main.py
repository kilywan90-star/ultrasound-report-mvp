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
import uuid
import hmac
import asyncio
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
    def _asr_unavailable(*a, **kw): raise RuntimeError("ASR不可用")
    transcribe_audio = _asr_unavailable

from templates import match_template, TEMPLATES
from template_filler import match_and_fill
from template_engine_v2 import match_and_fill_optimized, search_optimized as template_search_v2
from fixed_template_engine import process_with_fixed_template, TEMPLATE_TAGS, DEFAULT_TEMPLATES
from asr_correction import correct_ASR_text
from template_fetal import fill_fetal_template
from api_section_templates import router as section_templates_router
from api_pacs import router as pacs_router
from api_pacs_config import router as pacs_config_router
from api_system_log import router as syslog_router
from api_data_list import router as datalist_router
import db

BUILD = "20260607-0045"
VERSION = f"v3.1.{BUILD}"

from api_exam_parts import router as exam_parts_router
app = FastAPI(title="超声报告语音结构化", version=VERSION)

app.include_router(section_templates_router)
app.include_router(pacs_router)
app.include_router(pacs_config_router)
app.include_router(syslog_router)
app.include_router(datalist_router)
app.include_router(exam_parts_router)

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
        if path in ("/", "/api/health", "/docs", "/openapi.json"):
            return await call_next(request)
        # 检查 Authorization header
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            return JSONResponse({"detail": "未授权: 缺少API Token"}, status_code=401)
        token = auth[7:]
        if not hmac.compare_digest(token, API_TOKEN):
            return JSONResponse({"detail": "未授权: Token无效"}, status_code=403)
        return await call_next(request)

AUDIO_DIR = Path(__file__).parent / "audio_backups"
AUDIO_DIR.mkdir(exist_ok=True)

# ==================== 通用 ====================

@app.get("/api/health")
async def health():
    from asr_client import _load_hotwords
    hw_count = len(_load_hotwords())
    return {"status": "ok", "version": VERSION, "build": BUILD,
            "templates": 70, "asr_hotwords": hw_count}

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
    # 标准化性别: M/F → 男/女
    gender = {"M": "男", "F": "女"}.get(req.gender, req.gender)
    if gender not in ("男", "女"): raise HTTPException(400, "性别只能为 男 或 女")
    if req.age < 0 or req.age > 150: raise HTTPException(400, "年龄不合法(0-150)")
    if len(req.name.strip()) < 1: raise HTTPException(400, "姓名至少1个字符")
    if not req.exam_type.strip(): raise HTTPException(400, "检查类型不能为空")
    if len(req.exam_type.strip()) > 50: raise HTTPException(400, "检查类型过长(最多50字符)")
    patient = db.patient_add(req.name.strip(), gender, req.age, req.exam_type.strip(), req.exam_part)
    db.audit_log("patient_add", patient_id=patient["id"], input_text=f"{req.name},{req.gender},{req.age}",
                  output_text=f"patient_id={patient['id']}", detail={"exam_type": req.exam_type})
    return {"success": True, "patient": patient}

@app.get("/api/patients/queue")
async def patient_queue():
    return {"success": True, "patients": db.patient_queue()}

_VALID_STATUSES = {"待检", "检查中", "已完成", "已报告"}

@app.put("/api/patients/{patient_id}/status")
async def patient_update_status(patient_id: int, status: str = "检查中"):
    if status not in _VALID_STATUSES:
        raise HTTPException(400, f"状态值无效，可选: {_VALID_STATUSES}")
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
    if not re.fullmatch(r'[A-Za-z0-9_]+', audio_id):
        raise HTTPException(400, "audio_id格式无效")
    matches = list(AUDIO_DIR.glob(f"{audio_id}.*"))
    if not matches: raise HTTPException(404, "音频文件不存在")
    return FileResponse(matches[0])

@app.get("/api/audio/{audio_id}/download")
async def audio_download(audio_id: str):
    """下载原始录音到本机"""
    if not re.fullmatch(r'[A-Za-z0-9_]+', audio_id):
        raise HTTPException(400, "audio_id格式无效")
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
        from asr_client import _load_hotwords
        hw_count = len(_load_hotwords())
        result = await transcribe_audio(audio_bytes)
        logging.info(f"ASR转写成功: 热词{hw_count}个, 原始{len(result['raw'])}字, 纠错{len(result['text'])}字")
    except Exception as e:
        raise HTTPException(500, f"语音识别失败: {e}")

    return {"success": True, "raw_text": result["raw"], "text": result["text"], "audio_id": audio_id,
            "correction_stats": result.get("correction_stats")}

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
    # ASR纠错统计 (由 /api/transcribe 透传)
    correction_stats: dict | None = None

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


def _sanitize_pii(text: str, patient_id: str | None = None) -> str:
    """数据脱敏：移除姓名、住院号、门诊号等PII后传给LLM"""
    # 通用正则脱敏始终执行（手机号/身份证号）
    text = re.sub(r'1[3-9]\d{9}', '[手机号]', text)
    text = re.sub(r'\d{6}(19|20)\d{2}(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])\d{3}[\dXx]', '[身份证号]', text)
    if not patient_id:
        return text
    try:
        pid = int(patient_id)
        p = db.patient_get(pid)
        if p:
            if p.get("name"):
                text = text.replace(p["name"], "[患者]")
            if p.get("inpatient_id"):
                text = text.replace(p["inpatient_id"], "[住院号]")
            if p.get("outpatient_id"):
                text = text.replace(p["outpatient_id"], "[门诊号]")
    except Exception as e:
        logging.warning(f"PII脱敏DB查询失败: patient_id={patient_id}, error={e}")
    return text


def _run_fast_validation(filled_html: str, exam_type: str) -> list[str]:
    """快速通道验证层: L5(矛盾检测) + L6(数值范围校验)

    Returns:
        list[str]: 验证问题列表，空列表表示通过
    """
    import re as _re
    from rule_engine import get_rule
    issues = []

    # L5: 矛盾描述检测
    contradictions = [(c["negative"], c["positive"]) for c in get_rule("validation.contradictions", [])]
    try:
        antonym_pairs = _build_antonym_contradictions(exam_type)
        contradictions += [([a], [b]) for a, b in antonym_pairs]
    except Exception:
        pass

    filled_clean = re.sub(r'<[^>]+>', '', filled_html or "")
    for neg_list, pos_list in contradictions:
        has_neg = any(kw in filled_clean for kw in neg_list)
        has_pos = any(kw in filled_clean for kw in pos_list)
        if has_neg and has_pos:
            issues.append(f"L5: 矛盾描述 '{neg_list[0]}'+'{pos_list[0]}'")

    # L6: 数值范围校验
    try:
        from validators import validate_numerical_ranges
        range_warnings = validate_numerical_ranges(filled_html)
        for rw in range_warnings:
            if rw.get("severity") == "error":
                issues.append(f"L6: {rw['message']}")
    except Exception:
        pass

    return issues


@app.post("/api/structure")
async def structure(req: StructureRequest):
    """精简结构化: ASR->模板匹配->1次LLM填变量->输出"""
    import time as _time, json as _json, re as _re
    t0 = _time.time()

    if not req.text or not req.text.strip():
        raise HTTPException(400, "文本为空")
    if len(req.text) > 10000:
        raise HTTPException(400, "文本过长")

    from rule_engine import get_rule
    from template_loader import search_candidates, get_template_by_name, load_templates
    load_templates()

    A = correct_ASR_text(req.text)
    warnings = []

    # L0: short text gate
    _meaningful = _re.sub(r'[\s嗯啊哦呃额呢吧啦噢哦\W]', '', A)
    if len(_meaningful) < 8:
        raise HTTPException(400, f"录音内容过短（有效字符仅{len(_meaningful)}个），请重新录音")

    # Sex guard
    sex_conflict = detect_sex_conflict(A, req.patient_gender)
    if sex_conflict:
        warnings.append(sex_conflict)
        A = mask_conflict_organs(A, req.patient_gender)

    # Fetal fast path
    fetal_kw = get_rule("pipeline.fetal_path.keywords", ["产科","胎儿","四维","排畸","BPD","双顶径","股骨长"])
    is_fetal = any(kw in (req.exam_type + A[:80]) for kw in fetal_kw)
    if is_fetal and req.patient_gender != "男":
        report = fill_fetal_template(A)
        report = _wrap_hints_with_toggle(report)

        # Save to reports table (same as normal path)
        if req.patient_id and req.patient_id.strip():
            try:
                pid = int(req.patient_id)
                db.report_create(pid, "胎儿超声", req.text, _filter_checked(report))
            except Exception as e:
                logging.warning(f"胎儿报告保存失败: {e}")

        # Save trace log
        db.audit_log("fetal_template", patient_id=int(req.patient_id) if (req.patient_id and req.patient_id.strip()) else None,
                      input_text=req.text[:300], output_text=_extract_plain_text(report.get("study_see", ""))[:300])

        return _make_response(report, req, "fetal_template", "胎儿超声标准模板", 0.9, warnings, A)

    # Step1: Pattern match
    candidates = search_candidates(A, req.exam_type, limit=8)
    best_score = candidates[0]["score"] if candidates else 0
    best_name = candidates[0]["name"] if candidates else ""
    template_info1 = candidates[0].get("info1", "") if candidates else ""
    if not template_info1 and best_name:
        tpl = get_template_by_name(best_name)
        if tpl: template_info1 = tpl.get("info1", "")

    # Step1.5: 多器官综合描述检测（≥3个器官或>100字符时走LLM综合报告）
    _organ_kw = ["肝脏","胆囊","胰腺","脾脏","双肾","子宫","卵巢","附件","甲状腺","乳腺","心脏","颈动脉","前列腺","膀胱"]
    _organ_count = sum(1 for o in _organ_kw if o in A)
    is_multi = _organ_count >= 3 or (len(A) > 100 and _organ_count >= 2)

    if is_multi and not is_fetal:
        report = _llm_multi_organ_fill(A, req.exam_type)
        method = "llm_multi"
        best_name = "多器官综合报告"
    else:
        # Step2: 转换模板路径 (结构化3色HTML)
        from template_converted import lookup_template, setup as _tc_setup
        _tc_setup()
        converted = lookup_template(best_name) if best_name else None
        if converted and best_score >= 100 and not is_fetal:
            from template_converted.fill import fill_converted_template
            from template_converted.measurements import ALL as _ALL_MEAS
            from template_converted.options import ALL as _ALL_OPTS
            cat = converted.get("category", "")
            measurements = _ALL_MEAS.get(cat, _ALL_MEAS.get("abdomen", []))
            options_list = _ALL_OPTS.get(cat, []) + _ALL_OPTS.get("common", [])
            report = fill_converted_template(A, converted.get("html", template_info1), converted.get("fields", {}), measurements, options_list, {}, set())
            method = "converted_fill"
        elif best_score >= 50 and template_info1 and len(template_info1) >= 20:
            if best_score >= 200:
                from template_filler import match_and_fill as _rule_fill
                rule_result = _rule_fill(A)
                report = rule_result or {"study_see": template_info1, "study_hint": [], "recommendation": ""}
                method = "rule_fill"
            else:
                report = _llm_fill_template(A, req.exam_type, best_name, template_info1)
                method = "template_fill"
        else:
            report = _llm_free_generate(A, req.exam_type)
            method = "llm_free"
            best_name = "自由生成(无匹配模板)"

    report = _wrap_hints_with_toggle(report)

    # Numerical preservation
    report, warnings = _preserve_numbers(A, report, warnings)

    # Save
    report_id = None; pid = None
    if req.patient_id and req.patient_id.strip():
        try:
            pid = int(req.patient_id)
            r = db.report_create(pid, match_template(req.exam_type), req.text, _filter_checked(report))
            report_id = r["id"]
        except Exception as e:
            logging.warning(f"报告保存失败: {e}")

    elapsed_ms = int((_time.time() - t0) * 1000)
    _save_trace_simple(req, pid, A, report, best_name, method, elapsed_ms, warnings)

    return _make_response(report, req, method, best_name, 0.85, warnings, A)


def _llm_fill_template(asr_text, exam_type, tpl_name, info1):
    """1 LLM call: verify template + fill variables + extra content append"""
    from llm_client import _get_client, _parse_json
    client = _get_client(provider="deepseek" if os.getenv("DEEPSEEK_API_KEY") else "dashscope")
    model = "deepseek-v4-flash" if os.getenv("DEEPSEEK_API_KEY") else "qwen-plus"

    system = f"""超声科主任医师。将ASR口述填入固定模板。

模板名: {tpl_name}
模板正文:
{info1[:1000]}

规则:
1. ASR数值填入模板变量({{变量}})和占位符(___mm)
2. [选项A;选项B]只保留ASR提到的选项
3. ASR有但模板没有的内容追加到末尾, 用"补充: ..."标记
4. ASR缺失的变量保留 ___mm 不编造
5. 只输出JSON: {{"study_see":"...", "study_hint":[{{"rank":1,"diagnosis":"...","icd10":"..."}}], "recommendation":"..."}}"""

    try:
        resp = client.chat.completions.create(
            model=model, temperature=0.1, max_tokens=4096, timeout=40,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": f"ASR口述:\n{asr_text[:800]}"},
            ],
        )
        content = resp.choices[0].message.content
        if content:
            return _parse_json(content)
    except Exception as e:
        logging.warning(f"LLM fill failed: {e}")

    return {"study_see": f"<div class='rpt-html'>{asr_text}</div>", "study_hint": [], "recommendation": ""}


def _llm_multi_organ_fill(asr_text, exam_type):
    """多器官综合描述 — 用LLM生成完整的逐器官报告"""
    from llm_client import _get_client, _parse_json
    client = _get_client(provider="volc")
    model = "doubao-seed-1-6-flash-250615"

    import re
    all_organs = ["乳腺","甲状腺","胆囊","肝脏","胰腺","脾脏","双肾","子宫","卵巢","附件","前列腺","膀胱","心脏","颈动脉"]
    found_organs = [o for o in all_organs if o in asr_text]

    system = f"""一位资深超声科主任医师，将口语口述转为规范化超声报告。
检查类型: {exam_type}
涉及器官: {', '.join(found_organs) if found_organs else exam_type}

规则:
1. 按器官逐项输出，每个器官独立一行
2. 数值用原文，单位用mm或cm，用<b class="voice">值</b>标记
3. 缺失值填___mm
4. 覆盖所有涉及器官，每个器官都出现（包括正常的）
5. 口语转术语(乘→×, 小水泡→无回声区)
6. 只输出JSON: {{"study_see":"...", "study_hint":[{{"rank":1,"diagnosis":"...","icd10":"..."}}], "recommendation":"..."}}

示例:
输入: "右侧乳腺外上象限见一个0.8×0.5cm结节。胆囊见一个1.2cm强回声团。甲状腺左叶见一个0.3×0.2cm无回声结节。"
输出: {{"study_see":"乳腺: 右侧外上象限可见大小约0.8×0.5cm低回声结节，边界清晰。\\n胆囊: 大小正常，壁上可见大小约1.2cm强回声团，后伴声影。\\n甲状腺: 左叶可见大小约0.3×0.2cm无回声结节。\\n肝脏: 大小形态正常。\\n胰腺: 正常。\\n脾脏: 未见肿大。\\n双肾: 正常。", "study_hint":[{{"rank":1,"diagnosis":"乳腺结节","icd10":"N60.8"}},{{"rank":2,"diagnosis":"胆囊结石","icd10":"K80.2"}}], "recommendation":"建议专科随访。"}}"""

    for attempt in range(2):
        try:
            response = client.chat.completions.create(
                model=model, temperature=0.1, max_tokens=4096, timeout=30,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": f"请将以下口述转为规范化报告:\n\n{asr_text[:2000]}"},
                ])
            content = response.choices[0].message.content
            if content:
                return _parse_json(content)
        except Exception as e:
            if attempt < 1:
                import time
                time.sleep(1)
                continue
            logging.warning(f"多器官填充失败: {e}")

    return {"study_see": f"<div class='rpt-html'>{asr_text}</div>", "study_hint": [], "recommendation": ""}


def _llm_free_generate(asr_text, exam_type):
    """Pure LLM generation (no template match)"""
    from llm_client import generate_free_report
    return generate_free_report(asr_text, exam_type)


def _make_response(report, req, method, template, confidence, warnings, A):
    return {
        "success": True, "report": report, "report_id": None,
        "method": method, "warnings": warnings,
        "template_used": template, "confidence": confidence,
        "conflicts": [],
        "sources": {"A_asr": A[:500]},
    }


def _preserve_numbers(A, report, warnings):
    import re as _re3
    _asr_meas = _re3.findall(r'(?:约|大?小约?|长(?:约)?)?\s*\d+(?:\.\d+)?\s*[×xX\*乘]\s*\d+(?:\.\d+)?\s*(?:mm|毫米|cm|厘米)?', A)
    _asr_single = _re3.findall(r'(?:约|大?小约?|厚约?|长约?|深约?|宽约?|内径约?)\s*\d+(?:\.\d+)?\s*(?:mm|毫米|cm|厘米)', A)
    _all_vals = list(dict.fromkeys(_asr_meas + _asr_single))
    _plain = _re3.sub(r'<[^>]+>', '', report.get("study_see", ""))
    _missing = []
    for val in _all_vals:
        _clean = _re3.sub(r'[约大小长厚深宽内径]', '', val).strip()
        _nums = _re3.findall(r'\d+(?:\.\d+)?', _clean)
        if _nums and not any(n in _plain for n in _nums):
            _missing.append(val)
    if _missing:
        report["study_see"] = report.get("study_see", "") + "<br><b class='voice'>补充测量: " + "，".join(_missing) + "</b>"
        warnings.append(f"数值保全: {len(_missing)}个测量值追加到报告末尾")
    return report, warnings


def _save_trace_simple(req, pid, A, report, template_name, method, elapsed_ms, warnings):
    import json as _json
    from datetime import datetime as _dt
    try:
        now = _dt.now()
        c = db._conn()
        c.execute("""
            CREATE TABLE IF NOT EXISTS abcdef_trace_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                trace_id TEXT UNIQUE NOT NULL,
                patient_id INTEGER, gender TEXT, age INTEGER,
                A_asr TEXT, B_free_llm TEXT, C_regex TEXT,
                D_enhanced TEXT, E_template TEXT, F_validated TEXT,
                study_see TEXT, study_hint TEXT, recommendation TEXT,
                created_at TEXT NOT NULL, error_msg TEXT,
                template_name TEXT, template_id TEXT
            )
        """)
        _base = now.strftime("%Y%m%d%H%M%S") + now.strftime("%f")[:3]
        _seq = 1
        while True:
            _rid = f"{_base}{_seq:03d}"
            if not c.execute("SELECT id FROM abcdef_trace_log WHERE trace_id=?", (_rid,)).fetchone():
                break
            _seq += 1
        see = _extract_plain_text(report.get("study_see", ""))[:5000]
        hints = _json.dumps(report.get("study_hint", []), ensure_ascii=False)[:2000]
        rec = (report.get("recommendation", "") or "")[:2000]
        c.execute("""
            INSERT INTO abcdef_trace_log (trace_id,patient_id,gender,age,
                A_asr,B_free_llm,C_regex,study_see,study_hint,recommendation,
                created_at,error_msg,template_name,template_id)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            _rid, pid, req.patient_gender or "", req.patient_age or 0,
            A[:5000],
            _json.dumps({"method": method, "template": template_name}, ensure_ascii=False)[:5000],
            "simplified_v1",
            see, hints, rec,
            now.strftime("%Y-%m-%d %H:%M:%S"),
            "; ".join(warnings)[:1000] if warnings else None,
            template_name[:500] if template_name else None,
            template_name[:200] if template_name else None,
        ))
        c.commit()
    except Exception:
        pass  # trace log 非关键路径，不影响主流程


def _extract_plain_text(html_or_text: str) -> str:
    text = re.sub(r'<[^>]+>', '', html_or_text or "")
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


# ==================== ABCDEF 全链路日志 ====================

def _save_abcdef_trace(req, pid, A, B, C, D, EF, template_name, warnings):
    """每次ABCDEF结构化完成都写入全链路日志"""
    import json as _json, time as _time
    from datetime import datetime as _dt
    now = _dt.now()
    # ID: 年月日时分秒毫秒 + 3位自增
    _base = now.strftime("%Y%m%d%H%M%S") + now.strftime("%f")[:3]
    _seq = 1
    while True:
        _rid = f"{_base}{_seq:03d}"
        try:
            c = db._conn()
            if not c.execute("SELECT id FROM abcdef_trace_log WHERE trace_id=?", (_rid,)).fetchone():
                break
            _seq += 1
        except Exception:
            break
    gender = req.patient_gender or ""
    age = req.patient_age or 0
    c = db._conn()
    c.execute("""
        CREATE TABLE IF NOT EXISTS abcdef_trace_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trace_id TEXT UNIQUE NOT NULL,
            patient_id INTEGER, gender TEXT, age INTEGER,
            A_asr TEXT, B_free_llm TEXT, C_regex TEXT,
            D_enhanced TEXT, E_template TEXT, F_validated TEXT,
            study_see TEXT, study_hint TEXT, recommendation TEXT,
            created_at TEXT NOT NULL, error_msg TEXT,
            template_name TEXT, template_id TEXT
        )
    """)
    # 提取最终输出 (从 EF 和 B 路取最终报告)
    _final_see = EF.get("filled_study_see_html", "") if EF else ""
    _final_see = _extract_plain_text(_final_see)[:5000]
    _final_hints = _json.dumps(EF.get("study_hint", []), ensure_ascii=False)[:2000] if EF else ""
    _final_rec = (EF.get("recommendation", "") or "")[:2000] if EF else ""
    c.execute("""
        INSERT INTO abcdef_trace_log (trace_id,patient_id,gender,age,
            A_asr,B_free_llm,C_regex,D_enhanced,E_template,F_validated,
            study_see,study_hint,recommendation,
            created_at,error_msg,template_name,template_id)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (
        _rid, pid, gender, age,
        A[:5000],
        _json.dumps(B, ensure_ascii=False)[:5000] if B else None,
        _json.dumps(C, ensure_ascii=False)[:5000] if C else None,
        _json.dumps(D, ensure_ascii=False)[:5000] if D else None,
        _json.dumps(EF, ensure_ascii=False)[:5000] if EF else None,
        _json.dumps({"template": template_name, "warnings": warnings}, ensure_ascii=False)[:2000],
        _final_see, _final_hints, _final_rec,
        now.strftime("%Y-%m-%d %H:%M:%S"),
        "; ".join(warnings)[:1000] if warnings else None,
        template_name[:500] if template_name else None,
        EF.get("template_name", "")[:200] if EF else None,
    ))
    c.commit()
    logging.info(f"ABCDEF trace saved: {_rid}")

# ==================== 反义词对矛盾检测 ====================
# 域到检查类型的映射
_DOMAIN_EXAM_MAP = {
    "abdomen": ["腹部", "肝胆", "泌尿", "脾", "胰"],
    "cardiac": ["心脏", "心超", "心彩"],
    "thyroid": ["甲状腺"],
    "vascular": ["血管", "颈动脉", "动脉", "静脉"],
    "obgyn": ["妇产", "子宫", "卵巢", "妇科", "产科"],
    "fetal": ["产科", "胎儿", "四维", "排畸"],
    "tcd": ["TCD", "经颅"],
}

_antonym_cache: dict[str, list[tuple]] = {}

def _build_antonym_contradictions(exam_type: str) -> list[tuple]:
    """
    从 antonym_pairs.json 构建矛盾检测对
    
    返回: [(negative_term, positive_term), ...] 用于L5矛盾检测
    """
    if exam_type in _antonym_cache:
        return _antonym_cache[exam_type]
    
    try:
        from knowledge.loader import get_kb
        antonym_data = get_kb().antonym_pairs
    except Exception:
        _antonym_cache[exam_type] = []
        return []
    
    if not antonym_data:
        _antonym_cache[exam_type] = []
        return []
    
    # 确定当前检查类型匹配的域
    matched_domains = set()
    for domain, keywords in _DOMAIN_EXAM_MAP.items():
        if any(kw in exam_type for kw in keywords):
            matched_domains.add(domain)
    
    # 始终包含 general 域
    matched_domains.add("general")
    
    pairs = []
    
    def _extract_pairs_from_obj(obj, path=""):
        """递归提取反义词对，跳过 opt_* 键"""
        if isinstance(obj, dict):
            for k, v in obj.items():
                if k.startswith("opt_"):
                    continue  # 跳过选项列表
                _extract_pairs_from_obj(v, f"{path}.{k}")
        elif isinstance(obj, list) and len(obj) == 2:
            # 两个元素的列表视为 [正常, 异常] 对
            term_a, term_b = obj[0], obj[1]
            # 过滤: 两个词都必须 >= 2 字符，避免单字误匹配
            if len(term_a) >= 2 and len(term_b) >= 2:
                pairs.append((term_a, term_b))
    
    # 从匹配的域中提取
    for domain in matched_domains:
        if domain in antonym_data:
            _extract_pairs_from_obj(antonym_data[domain], domain)
    
    _antonym_cache[exam_type] = pairs
    return pairs


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
    if not report:
        raise HTTPException(400, "报告数据不能为空")
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


# ==================== 模板查看/编辑 API ====================

@app.get("/api/template/search")
async def search_template(q: str = "", module: str = ""):
    """搜索模板：按关键词或模块名搜索，返回匹配模板列表（含完整内容）"""
    from template_loader import load_templates, search_candidates, get_template_by_name
    templates = load_templates()
    if not templates:
        return {"success": True, "templates": []}
    if q:
        results = search_candidates(q, limit=20)
        # 补充完整内容
        for r in results:
            full = get_template_by_name(r["name"])
            if full:
                r["info1"] = full.get("info1", "")
                r["info2"] = full.get("info2", "")
        return {"success": True, "templates": results}
    if module:
        matches = [t for t in templates.values() if t.get("module") == module]
        return {"success": True, "templates": matches[:30]}
    return {"success": True, "templates": list(templates.values())[:30]}


@app.get("/api/template/{name}")
async def get_template(name: str):
    """获取单条模板的完整内容"""
    from template_loader import get_template_by_name
    tpl = get_template_by_name(name)
    if not tpl:
        raise HTTPException(404, f"模板 '{name}' 不存在")
    return {"success": True, "template": tpl}


@app.put("/api/template/{name}")
async def update_template(name: str, body: dict):
    """更新模板内容（保存到内存，重启后从CSV重新加载）"""
    from template_loader import load_templates, _template_index
    load_templates()
    if name not in _template_index:
        raise HTTPException(404, f"模板 '{name}' 不存在")
    if "info1" in body:
        _template_index[name]["info1"] = body["info1"]
    if "info2" in body:
        _template_index[name]["info2"] = body["info2"]
    logging.info(f"模板已更新: {name}")
    return {"success": True, "message": f"模板 '{name}' 已保存"}

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
