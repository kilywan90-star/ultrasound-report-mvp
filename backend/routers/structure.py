import asyncio
"""
超声语音报告系统 - 结构化管线路由 (核心)
(从 main.py 拆出的内联路由)
"""
import re, json, time as _time, logging, hashlib
from datetime import datetime
from pathlib import Path
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from collections import OrderedDict

import db
from asr_correction import correct_ASR_text
from templates import match_template
from template_loader import search_candidates, get_template_by_name, load_templates
from template_filler import match_and_fill as _rule_fill
from template_fetal import fill_fetal_template

# ─── 本地微调模型 (替换火山方舟LLM) ───
_USE_LOCAL_LLM = True   # True=用本地merged model(免费), False=火山方舟(付费)
try:
    from llm_local import load_model as _local_load, generate as _local_gen, generate_structured, generate_free_report as _local_free
    _LOCAL_LLM_AVAILABLE = True
    # 预加载模型
    _local_load()
except Exception as e:
    _LOCAL_LLM_AVAILABLE = False
    _USE_LOCAL_LLM = False
    print(f"[本地LLM] 不可用: {e}")

router = APIRouter(tags=["结构化"])


# ==================== LLM 调用缓存 ====================

class LLMCache:
    """内存缓存 LLM 调用结果（LRU，最多 500 条）"""
    def __init__(self, maxsize: int = 500):
        self._cache: OrderedDict[str, str] = OrderedDict()
        self._maxsize = maxsize

    def _key(self, text: str, exam_type: str, tpl_name: str = "") -> str:
        return hashlib.md5(f"{text}|{exam_type}|{tpl_name}".encode()).hexdigest()

    def get(self, text: str, exam_type: str, tpl_name: str = "") -> str | None:
        k = self._key(text, exam_type, tpl_name)
        if k in self._cache:
            self._cache.move_to_end(k)
            return self._cache[k]
        return None

    def set(self, text: str, exam_type: str, result: str, tpl_name: str = "") -> None:
        k = self._key(text, exam_type, tpl_name)
        self._cache[k] = result
        if len(self._cache) > self._maxsize:
            self._cache.popitem(last=False)

    def clear(self) -> None:
        self._cache.clear()


_llm_cache = LLMCache(500)
_llm_cache_hits = 0
_llm_cache_miss = 0


def cache_hit_rate() -> str:
    total = _llm_cache_hits + _llm_cache_miss
    return f"{_llm_cache_hits}/{total} ({(_llm_cache_hits/total*100 if total else 0):.0f}%)"


# ==================== 模型 ====================

class StructureRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=10000)
    exam_type: str = Field(default="腹部超声", max_length=50)
    patient_id: str | None = None
    patient_name: str | None = None
    patient_gender: str | None = None
    patient_age: int | None = None
    clinical_diag: str | None = None
    correction_stats: dict | None = None


# ==================== 辅助函数 ====================

def _wrap_hints_with_toggle(report: dict) -> dict:
    """给 study_hint 每条包裹 checked + id，并过滤非dict条目"""
    hints = report.get("study_hint", [])
    clean = []
    for i, h in enumerate(hints):
        if isinstance(h, str):
            clean.append({"rank": i + 1, "diagnosis": h, "icd10": "", "id": f"h{i}", "checked": True})
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


def _extract_plain_text(html_or_text: str) -> str:
    text = re.sub(r'<[^>]+>', '', html_or_text or "")
    text = re.sub(r'\s+', ' ', text)
    return text.strip()




def _save_api_report(req, A, report, template_name):
    """保存标准化报告到 api_reports 表（供外部系统拉取）"""
    import re as _re
    try:
        hints = report.get("study_hint", [])
        diag_text = "; ".join(h.get("diagnosis", "") for h in hints if h.get("diagnosis"))
        see_text = _re.sub(r'<[^>]+>', '', report.get("study_see", "") or "")
        c = db._conn()
        c.execute("""
            INSERT INTO api_reports(examdate,examtime,VISCERAS,NAME,SEX,age,
                DESCRIBES,DIAGNOSIS,ModuleName)
            VALUES(date('now','localtime'),time('now','localtime'),?,?,?,?,?,?,?)
        """, (
            str(req.exam_type or ''),
            str(req.patient_name or ''),
            str(req.patient_gender or ''),
            int(req.patient_age or 0),
            str(see_text[:2000]),
            str(diag_text[:500]),
            str(template_name or ''),
        ))
        c.commit()
    except Exception as e:
        logging.debug(f"api_reports写入失败(非关键): {e}")


def _make_response(report, req, method, template, confidence, warnings, A, elapsed_ms=0):
    return {
        "success": True, "report": report, "report_id": None,
        "method": method, "warnings": warnings,
        "template_used": template, "confidence": confidence,
        "conflicts": [], "elapsed_ms": elapsed_ms,
        "sources": {"A_asr": A[:500]},
    }


def _run_fast_validation(filled_html: str, exam_type: str) -> list[str]:
    """快速通道验证层: L5(矛盾检测) + L6(数值范围校验)"""
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
        from validators.numerical import validate_numerical_ranges
        range_warnings = validate_numerical_ranges(filled_html)
        for rw in range_warnings:
            if rw.get("severity") == "error":
                issues.append(f"L6: {rw['message']}")
    except Exception:
        pass

    return issues


def _preserve_numbers(A, report, warnings):
    """数值保全：捕获ASR中所有数值，确保出现在报告或补充到末尾"""
    _asr_meas = re.findall(r'\d+(?:\.\d+)?\s*[×xX\*乘]\s*\d+(?:\.\d+)?(?:\s*[×xX\*乘]\s*\d+(?:\.\d+)?)?\s*(?:mm|毫米|cm|厘米)?', A)
    _asr_single = re.findall(r'(?:约|大小约|厚约|长约|宽约|深约|内径约|分离约)?\s*\d+(?:\.\d+)?\s*(?:mm|毫米|cm|厘米)', A)
    _asr_nums = re.findall(r'(?<![×\d])\d+(?:\.\d+)?(?=\s*(?:×|mm|毫米|cm|厘米|[，。\s]))', A)
    _all_vals = list(dict.fromkeys(_asr_meas + _asr_single))
    _plain = re.sub(r'<[^>]+>', '', report.get("study_see", ""))
    _missing = []
    for val in _all_vals:
        _nums = re.findall(r'\d+(?:\.\d+)?', str(val))
        if _nums and not any(n in _plain for n in _nums):
            _missing.append(val)
    if _missing:
        appendix = "，".join(str(v) for v in _missing)
        report["study_see"] = report.get("study_see", "") + f"<br><b class='voice'>补充测量: {appendix}</b>"
        warnings.append(f"数值保全: {len(_missing)}个测量值追加到报告末尾")
    return report, warnings

def _save_trace_simple(req, pid, A, report, template_name, method, elapsed_ms, warnings):
    try:
        now = datetime.now()
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
        hints = json.dumps(report.get("study_hint", []), ensure_ascii=False)[:2000]
        rec = (report.get("recommendation", "") or "")[:2000]
        c.execute("""
            INSERT INTO abcdef_trace_log (trace_id,patient_id,gender,age,
                A_asr,B_free_llm,C_regex,study_see,study_hint,recommendation,
                created_at,error_msg,template_name,template_id)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            _rid, pid, req.patient_gender or "", req.patient_age or 0,
            A[:5000],
            json.dumps({"method": method, "template": template_name}, ensure_ascii=False)[:5000],
            "simplified_v1",
            see, hints, rec,
            now.strftime("%Y-%m-%d %H:%M:%S"),
            "; ".join(warnings)[:1000] if warnings else None,
            template_name[:500] if template_name else None,
            template_name[:200] if template_name else None,
        ))
        c.commit()
    except Exception:
        pass  # trace log 非关键路径


def _save_abcdef_trace(req, pid, A, B, C, D, EF, template_name, warnings):
    """每次ABCDEF结构化完成都写入全链路日志"""
    now = datetime.now()
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
    _final_see = EF.get("filled_study_see_html", "") if EF else ""
    _final_see = _extract_plain_text(_final_see)[:5000]
    _final_hints = json.dumps(EF.get("study_hint", []), ensure_ascii=False)[:2000] if EF else ""
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
        json.dumps(B, ensure_ascii=False)[:5000] if B else None,
        json.dumps(C, ensure_ascii=False)[:5000] if C else None,
        json.dumps(D, ensure_ascii=False)[:5000] if D else None,
        json.dumps(EF, ensure_ascii=False)[:5000] if EF else None,
        json.dumps({"template": template_name, "warnings": warnings}, ensure_ascii=False)[:2000],
        _final_see, _final_hints, _final_rec,
        now.strftime("%Y-%m-%d %H:%M:%S"),
        "; ".join(warnings)[:1000] if warnings else None,
        template_name[:500] if template_name else None,
        EF.get("template_name", "")[:200] if EF else None,
    ))
    c.commit()
    logging.info(f"ABCDEF trace saved: {_rid}")


# ==================== 反义词对矛盾检测 ====================

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
    """从 antonym_pairs.json 构建矛盾检测对"""
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

    matched_domains = set()
    for domain, keywords in _DOMAIN_EXAM_MAP.items():
        if any(kw in exam_type for kw in keywords):
            matched_domains.add(domain)
    matched_domains.add("general")

    pairs = []

    def _extract_pairs_from_obj(obj, path=""):
        if isinstance(obj, dict):
            for k, v in obj.items():
                if k.startswith("opt_"):
                    continue
                _extract_pairs_from_obj(v, f"{path}.{k}")
        elif isinstance(obj, list) and len(obj) == 2:
            term_a, term_b = obj[0], obj[1]
            if len(term_a) >= 2 and len(term_b) >= 2:
                pairs.append((term_a, term_b))

    for domain in matched_domains:
        if domain in antonym_data:
            _extract_pairs_from_obj(antonym_data[domain], domain)

    _antonym_cache[exam_type] = pairs
    return pairs


# ==================== 建议生成（规则+LLM并行）====================

# 异常规则（优先匹配，防止正常规则误拦截）
_ABNORMAL_RULES = [
    (lambda see, name, text, exam: "脂肪肝" in see or "脂肪肝" in name or "脂肪肝" in text, "建议低脂饮食，定期复查"),
    (lambda see, name, text, exam: "结石" in see or "结石" in name or "结石" in text, "建议定期复查，注意饮食"),
    (lambda see, name, text, exam: "囊肿" in see or "囊肿" in text, "建议定期复查"),
    (lambda see, name, text, exam: "增生" in see or "增生" in text, "建议定期复查"),
    (lambda see, name, text, exam: "结节" in see or "结节" in text, "建议专科就诊，定期复查"),
    (lambda see, name, text, exam: "肌瘤" in see or "肌瘤" in text, "建议定期复查"),
    (lambda see, name, text, exam: "斑块" in see or "斑块" in text, "建议控制血脂，定期复查"),
    (lambda see, name, text, exam: "积液" in see or "积液" in text, "建议专科就诊"),
    (lambda see, name, text, exam: "钙化" in see or "钙化" in text, "建议定期复查"),
    (lambda see, name, text, exam: "胎儿" in text and "产" in exam, "建议定期产检"),
]

# 正常规则（仅当无异常模式命中时触发）
_NORMAL_RULES = [
    (lambda see, name, text, exam: "未见明显异常" in see, "建议定期体检"),
    (lambda see, name, text, exam: "未见异常" in see, "建议定期体检"),
    (lambda see, name, text, exam: all(kw in see for kw in ["大小正常", "回声均匀"]), "建议定期体检"),
]


def _quick_recommendation(asr_text: str, template_name: str, report: dict, exam_type: str) -> str | None:
    """规则快速判断（0ms，无LLM）。返回建议或None"""
    if not report or not report.get("study_see"):
        return None
    _study_see_plain = re.sub(r'<[^>]+>', '', report.get("study_see", ""))[:500]

    # 异常规则优先（同时检查 see + name + text）
    for rule_fn, suggestion in _ABNORMAL_RULES:
        try:
            if rule_fn(_study_see_plain, template_name, asr_text, exam_type):
                return suggestion
        except Exception:
            continue

    # 正常规则兜底（同时检查 see + text，因为study_see可能丢关键词）
    _combined = _study_see_plain + ' ' + asr_text
    for rule_fn, suggestion in _NORMAL_RULES:
        try:
            if rule_fn(_study_see_plain, template_name, asr_text, exam_type) or \
               rule_fn(_combined, template_name, asr_text, exam_type):
                return suggestion
        except Exception:
            continue

    return None


_SYSTEM_RECOMMEND_PROMPT = """超声科主任医师。基于超声所见内容, 生成简短临床建议。

规则:
1. 根据异常发现给出针对性的建议(复查/随访/专科就诊等)
2. 如果全部正常 → 建议"定期体检"
3. 建议不超过30个字, 简洁明确
4. 只输出建议文本, 不要JSON"""


def _call_llm_recommendation(asr_text: str, template_name: str, report: dict, exam_type: str) -> str:
    """同步LLM调用（在异步线程中执行）"""
    global _llm_cache_hits, _llm_cache_miss
    _study_see_plain = re.sub(r'<[^>]+>', '', report.get("study_see", ""))[:500]

    # 缓存检查
    cached = _llm_cache.get(asr_text, exam_type, template_name)
    if cached:
        _llm_cache_hits += 1
        return cached
    _llm_cache_miss += 1

    prompt = f"模板: {template_name}\n超声所见: {_study_see_plain}"

    try:
        if _USE_LOCAL_LLM and _LOCAL_LLM_AVAILABLE:
            result = _local_gen(prompt, system_prompt=_SYSTEM_RECOMMEND_PROMPT, max_tokens=128)
            if result:
                result = result.strip().strip('"').strip("'")[:60]
                _llm_cache.set(asr_text, exam_type, result, template_name)
                return result
        else:
            from llm_client import _get_client, _parse_json
            client = _get_client(provider="volc")
            resp = client.chat.completions.create(
                model="doubao-seed-1-6-flash-250615",
                temperature=0.1, max_tokens=128, timeout=8,
                messages=[
                    {"role": "system", "content": _SYSTEM_RECOMMEND_PROMPT},
                    {"role": "user", "content": prompt},
                ],
            )
            content = resp.choices[0].message.content
            if content:
                result = content.strip().strip('"').strip("'")[:60]
                _llm_cache.set(asr_text, exam_type, result, template_name)
                return result
    except Exception:
        pass
    return ""


async def _generate_recommendation(asr_text: str, template_name: str, report: dict, exam_type: str) -> str:
    """
    并行生成临床建议
    1. 规则快检（0ms）→ 命中即返回
    2. 未命中 → 用 asyncio.to_thread 在后台线程调LLM，不阻塞event loop
    """
    # Phase 1: 规则快检（0ms，不调LLM）
    rule_result = _quick_recommendation(asr_text, template_name, report, exam_type)
    if rule_result:
        return rule_result

    # Phase 2: LLM兜底（异步线程，不阻塞主协程）
    try:
        import asyncio
        result = await asyncio.wait_for(
            await asyncio.to_thread(_call_llm_recommendation, asr_text, template_name, report, exam_type),
            timeout=8.0,
        )
        if result:
            return result
    except (asyncio.TimeoutError, Exception):
        logging.debug("LLM建议生成超时或失败，返回空")
        pass

    return ""


def _llm_fill_template(asr_text, exam_type, tpl_name, info1):
    """1 LLM call: 将短文本片段展开为完整超声报告"""

    system = f"""超声科主任医师。基于口述片段生成完整规范的超声报告。

参考模板名: {tpl_name}
模板正文参考:
{info1[:1000]}

规则:
1. ASR明确提到的异常描述 → 原样保留
2. ASR没说的正常部分 → 根据模板上下文和医学常识, 合理补全为正常描述
   (如"大小形态正常"、"回声均匀"、"边界清晰"等)
3. ASR提到的数值 → 填入对应位置, 用<b class="voice">值</b>标记
4. 不要让报告看起来有缺失——ASR没提到的器官/测量按正常处理
5. 输出3色HTML格式:
   - ASR填入/推理的正常值: <b class="voice">值</b>
   - 无法确定的保留: <i class="unfill">__</i>
6. 只输出JSON: {{"study_see":"完整HTML...", "study_hint":[{{"rank":1,"diagnosis":"..."}}], "recommendation":"..."}}"""

    try:
        if _USE_LOCAL_LLM and _LOCAL_LLM_AVAILABLE:
            result = generate_structured(system, f"ASR口述:\n{asr_text[:800]}")
            if result.get("study_see"):
                return result
        else:
            from llm_client import _get_client, _parse_json
            client = _get_client(provider="volc")
            resp = client.chat.completions.create(
                model="doubao-seed-1-6-flash-250615", temperature=0.1, max_tokens=4096, timeout=40,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": f"ASR口述:\n{asr_text[:800]}"},
                ],
            )
            content = resp.choices[0].message.content
            if content:
                parsed = _parse_json(content)
                if parsed and parsed.get("study_see"):
                    return parsed
                if "<div" in content or "study_see" in content[:100]:
                    html_match = re.search(r'<div[^>]*class=.rpt-html.*?>.*?</div>', content, re.DOTALL)
                    if html_match:
                        return {"study_see": html_match.group(0), "study_hint": [], "recommendation": ""}
                    return {"study_see": f"<div class='rpt-html'>{re.sub(r'[\"{}\n\r]', ' ', content[:2000])}</div>", "study_hint": [], "recommendation": ""}
    except Exception as e:
        logging.warning(f"LLM fill failed: {e}")

    return {"study_see": f"<div class='rpt-html'>{asr_text}</div>", "study_hint": [], "recommendation": ""}


def _llm_complete_report(asr_text, tpl_name, template, report):
    """LLM智能补全: 推理医生没说但可推导的正常值(unfill→voice)"""
    if not report.get("study_see"):
        return report

    _current_see = report["study_see"]
    _plain = re.sub(r'<[^>]+>', '', _current_see)
    _fields_text = "\n".join(f"  {k}: {v}" for k, v in sorted(template.get("fields", {}).items())[:30])

    system = f"""超声科主任医师。补全报告的空白字段(unfill)。

ASR原文: {asr_text[:600]}
模板名: {tpl_name}
模板字段:
{_fields_text}

规则:
1. ASR数值 → 保留原值不动
2. <i class="unfill">__</i> → 根据模板字段名推理合理值
   - 大小/直径/径 → 若ASR没说, 推理为正常范围值或留空
   - 回声/形态/边界 → 推理为"正常"、"清晰"、"规则"
   - 血流/CDFI → 推理为"未见异常血流信号"
   - 厚度 → 若没说, 推理为正常参考值
3. 置信度: 能确定的填值, 不确定的保留___
4. 只输出修改后的完整study_see HTML! 不要包裹在JSON中!"""

    prompt = f"当前报告:\n{_current_see}"

    try:
        if _USE_LOCAL_LLM and _LOCAL_LLM_AVAILABLE:
            content = _local_gen(prompt, system_prompt=system, max_tokens=4096)
            if content and "unfill" in _current_see:
                if "<div" in content:
                    report["study_see"] = content
                try:
                    import json as _js
                    parsed = _js.loads(content)
                    if parsed and "study_see" in parsed:
                        report["study_see"] = parsed["study_see"]
                except: pass
            return report
        else:
            from llm_client import _get_client, _parse_json
            client = _get_client(provider="volc")
            resp = client.chat.completions.create(
                model="doubao-seed-1-6-flash-250615", temperature=0.1, max_tokens=4096, timeout=15,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
                ],
            )
            content = resp.choices[0].message.content.strip()
            if content and "unfill" in _current_see:
                if "<div" in content:
                    report["study_see"] = content
                elif content.startswith("{"):
                    parsed = _parse_json(content)
                    if parsed and "study_see" in parsed:
                        report["study_see"] = parsed["study_see"]
            return report
    except Exception as e:
        logging.warning(f"LLM智能补全失败: {e}")
        return report


def _llm_multi_organ_fill(asr_text, exam_type):
    """多器官综合描述 — 用LLM生成完整的逐器官报告"""

    all_organs = ["乳腺", "甲状腺", "胆囊", "肝脏", "胰腺", "脾脏", "双肾", "子宫", "卵巢", "附件", "前列腺", "膀胱", "心脏", "颈动脉"]
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
            if _USE_LOCAL_LLM and _LOCAL_LLM_AVAILABLE:
                result = _local_gen(f"请将以下口述转为规范化报告:\n\n{asr_text[:2000]}", system_prompt=system, max_tokens=4096)
                if result:
                    try:
                        import json as _js
                        parsed = _js.loads(result)
                        if parsed and parsed.get("study_see"):
                            return parsed
                    except: pass
                    if "<div" in result:
                        return {"study_see": result, "study_hint": [], "recommendation": ""}
            else:
                from llm_client import _get_client, _parse_json
                client = _get_client(provider="volc")
                model = "doubao-seed-1-6-flash-250615"
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
                import time as _sleep
                _sleep.sleep(1)
                continue
            logging.warning(f"多器官填充失败: {e}")

    return {"study_see": f"<div class='rpt-html'>{asr_text}</div>", "study_hint": [], "recommendation": ""}


def _llm_free_generate(asr_text, exam_type):
    """Pure LLM generation (no template match)"""
    from llm_client import generate_free_report
    return generate_free_report(asr_text, exam_type)


# ==================== 主结构化路由 ====================

@router.post("/api/structure")
async def structure(req: StructureRequest):
    """精简结构化: ASR->模板匹配->1次LLM填变量->输出"""
    t0 = _time.time()

    if not req.text or not req.text.strip():
        raise HTTPException(400, "文本为空")
    if len(req.text) > 10000:
        raise HTTPException(400, "文本过长")

    from rule_engine import get_rule
    load_templates()

    A = correct_ASR_text(req.text)
    warnings = []

    # L0: short text gate
    _meaningful = re.sub(r'[\s嗯啊哦呃额呢吧啦噢哦\W]', '', A)
    if len(_meaningful) < 3:
        raise HTTPException(400, f"录音内容过短（有效字符仅{len(_meaningful)}个），请重新录音")

    # L0.5: 口误检测
    _correction_pattern = r'(\d+(?:\.\d+)?)\s*(?:×\s*\d+(?:\.\d+)?)?\s*不对不对\s*(\d+(?:\.\d+)?(?:\s*×\s*\d+(?:\.\d+)?)?)'
    A = re.sub(_correction_pattern, r'\2', A)
    _change_pattern = r'(?:等一下|改一下|改成)[^。]*?(\d+(?:\.\d+)?)\s*(?:改成|改为)\s*(\d+(?:\.\d+)?)'
    A = re.sub(_change_pattern, r'\2', A)

    # Route: 预分类
    from routing import classify as _route
    _route_result = _route(A, req.exam_type)

    # Fetal fast path
    if _route_result["is_fetal"] and (req.patient_gender or "").strip() not in ("男", "M", "male"):
        report = fill_fetal_template(A)
        report = _wrap_hints_with_toggle(report)
        if req.patient_id and req.patient_id.strip():
            try:
                pid = int(req.patient_id)
                db.report_create(pid, "胎儿超声", req.text, _filter_checked(report))
            except Exception as e:
                logging.warning(f"胎儿报告保存失败: {e}")
        db.audit_log("fetal_template",
                     patient_id=int(req.patient_id) if (req.patient_id and req.patient_id.strip()) else None,
                     input_text=req.text[:300],
                     output_text=_extract_plain_text(report.get("study_see", ""))[:300])
        return _make_response(report, req, "fetal_template", "胎儿超声标准模板", 0.9, warnings, A)

    # Multi-organ LLM path
    if _route_result["is_multi"]:
        report = await asyncio.to_thread(_llm_multi_organ_fill, A, req.exam_type)
        report = _wrap_hints_with_toggle(report)
        report, warnings = _preserve_numbers(A, report, warnings)
        pid = None
        if req.patient_id and req.patient_id.strip():
            try:
                pid = int(req.patient_id)
                r = db.report_create(pid, match_template(req.exam_type), req.text, _filter_checked(report))
            except Exception as e:
                logging.warning(f"报告保存失败: {e}")
        elapsed_ms = int((_time.time() - t0) * 1000)
        _save_trace_simple(req, pid, A, report, "多器官综合报告", "llm_multi", elapsed_ms, warnings)
        return _make_response(report, req, "llm_multi", "多器官综合报告", 0.85, warnings, A)

    # Step1: Pattern match
    candidates = None
    _match_result_40k = None
    if _route_result.get("category") == "other":
        try:
            from match_engine import auto_match as _auto_match
            _match_result_40k = _auto_match(A)
        except Exception:
            pass

    candidates = search_candidates(A, req.exam_type, limit=8, category=_route_result.get("category"))
    best_score = candidates[0]["score"] if candidates else 0
    best_name = candidates[0]["name"] if candidates else ""
    template_info1 = candidates[0].get("info1", "") if candidates else ""

    # 跨类别保底: category过滤后得分偏低 → 降级全量搜索
    _search_category = _route_result.get("category")
    if _search_category and _search_category != "other" and best_score < 80:
        _full_candidates = search_candidates(A, req.exam_type, limit=8, category=None)
        _full_best_score = _full_candidates[0]["score"] if _full_candidates else 0
        if _full_best_score > best_score:
            candidates = _full_candidates
            best_score = _full_best_score
            best_name = _full_candidates[0]["name"] if _full_candidates else ""
            template_info1 = _full_candidates[0].get("info1", "") if _full_candidates else ""

    if not template_info1 and best_name:
        tpl = get_template_by_name(best_name)
        if tpl:
            template_info1 = tpl.get("info1", "")

    # 40万引擎覆盖
    if _match_result_40k and (_route_result.get("category") == "other" or best_score < 50):
        template_info1 = _match_result_40k.get("info1", template_info1)
        best_name = _match_result_40k.get("discname", best_name)
        best_score = max(best_score, 100)
        report = {
            "study_see": f"<div class='rpt-html'>{template_info1[:2000]}</div>",
            "study_hint": [{"rank": 1, "diagnosis": _match_result_40k.get("discname", ""), "icd10": ""}],
            "recommendation": "",
        }
        method = "converted_fill"
        report = _wrap_hints_with_toggle(report)
        report, warnings = _preserve_numbers(A, report, warnings)
        _llm_suggestion = await _generate_recommendation(A, best_name, report, req.exam_type)
        if _llm_suggestion:
            report["recommendation"] = _llm_suggestion
        # 同步写入 api_reports 存档表（供外部系统拉取）
        _save_api_report(req, A, report, best_name)

        return _make_response(report, req, method, best_name, 0.85, warnings, A)

    # 40万数据匹配引擎补充
    _match_hint = None
    if best_score < 100 or _route_result.get("category") == "other":
        try:
            from match_engine import auto_match as _auto_match, search as _match_search
            _match_result = _auto_match(A)
            if _match_result:
                _match_hint = _match_result
                if not template_info1 or len(template_info1) < 20:
                    template_info1 = _match_result.get("info1", template_info1)
                if not best_name:
                    best_name = _match_result.get("discname", "")
            if not template_info1 or len(template_info1) < 20:
                _top = _match_search(A, 1)
                if _top:
                    _match_hint = _top[0]
                    template_info1 = _top[0].get("info1", template_info1)
                    best_name = _top[0].get("discname", best_name)
        except Exception:
            pass

    # Step2: 路径分派
    from template_converted import lookup_template, setup as _tc_setup
    _tc_setup()
    converted = lookup_template(best_name) if best_name else None

    if converted and best_score >= 100:
        _better_name = best_name
        _better_converted = converted
        if len(candidates) >= 2:
            _asr_meas = len(re.findall(r'\d+(?:\.\d+)?\s*[×xX\*]', A))
            for _cand in candidates[1:4]:
                _cand_name = _cand["name"]
                if _cand["score"] >= best_score - 30:
                    _cand_conv = lookup_template(_cand_name)
                    if _cand_conv:
                        _cand_fields = _cand_conv.get("fields", {})
                        _cand_meas = len(_cand_fields)
                        if _cand_meas > len(converted.get("fields", {})) and _asr_meas >= _cand_meas:
                            _better_name = _cand_name
                            _better_converted = _cand_conv
                            break

        from template_converted.fill import fill_converted_template
        cat = _route_result.get("category", "abdomen")
        report = fill_converted_template(
            A,
            _better_converted.get("html", template_info1),
            _better_converted.get("fields", {}),
            _better_converted.get("measurements", []),
            _better_converted.get("options", []),
            _better_converted.get("opt_reset", {}),
            set(_better_converted.get("option_keys", [])),
        )
        best_name = _better_name
        method = "converted_fill"

        _see = report.get("study_see", "")
        _unfill_count = _see.count("unfill")
        _voice_count = _see.count("voice")
        if _unfill_count >= 4 and _unfill_count > _voice_count * 2:
            report = await asyncio.to_thread(_llm_complete_report, A, best_name, converted, report)
            method = "converted_fill_llm"
            logging.info(f"LLM补全: {best_name} unfill={_unfill_count} voice={_voice_count}")

        # 从模板名推断 study_hint（converted_fill 本身不生成 hints）
        if not report.get("study_hint") or len(report["study_hint"]) == 0:
            # 从 best_name 提取诊断词
            _diagnosis = best_name or ""
            if _diagnosis and _diagnosis != "自由生成(无匹配模板)":
                report["study_hint"] = [{"rank": 1, "diagnosis": _diagnosis, "icd10": ""}]
    elif best_score >= 200 and template_info1 and len(template_info1) >= 20:
        rule_result = _rule_fill(A)
        report = rule_result or {"study_see": template_info1, "study_hint": [], "recommendation": ""}
        method = "rule_fill"
    elif best_score >= 50 and template_info1 and len(template_info1) >= 20:
        report = await asyncio.to_thread(_llm_fill_template, A, req.exam_type, best_name, template_info1)
        method = "template_fill"
    elif best_score >= 30 and template_info1 and len(template_info1) >= 20:
        report = await asyncio.to_thread(_llm_fill_template, A, req.exam_type, best_name, template_info1)
        method = "template_fill_low"
    else:
        # 40万真实报告兜底: 当常规匹配都失败时, 用40W数据匹配
        _40w_candidates = None
        try:
            from matcher_40w import match_40w
            _40w_candidates = match_40w(A, req.exam_type, top_n=3)
        except Exception:
            pass

        if _40w_candidates:
            _40w_top = _40w_candidates[0]
            report = {
                "study_see": f"<div class='rpt-html'>{_40w_top['see'][:2000]}</div>",
                "study_hint": [{"rank": 1, "diagnosis": _40w_top['hint'][:200], "icd10": ""}],
                "recommendation": "",
            }
            method = "40w_match"
            best_name = _40w_top['hint'][:50] or "40万报告匹配"
            logging.info(f"40W fallback used: exam_type={req.exam_type} hint={_40w_top['hint'][:40]}")
        else:
            report = await asyncio.to_thread(_llm_free_generate, A, req.exam_type)
            method = "llm_free"
            best_name = "自由生成(无匹配模板)"

    report = _wrap_hints_with_toggle(report)
    report, warnings = _preserve_numbers(A, report, warnings)

    # L7: LLM建议生成
    if method not in ("fetal_template", "llm_multi"):
        _llm_suggestion = await _generate_recommendation(A, best_name, report, req.exam_type)
        if _llm_suggestion:
            report["recommendation"] = _llm_suggestion

    # 多器官兜底（排除"双肾"这种一个器官的变体）
    _all_organs = ["乳腺", "甲状腺", "胆囊", "肝脏", "胰腺", "脾脏", "子宫", "卵巢", "附件", "前列腺", "膀胱", "心脏", "颈动脉"]
    _all_organs_short = {"乳": "乳腺", "甲": "甲状腺", "肝": "肝脏", "胆": "胆囊", "脾": "脾脏", "肾": "肾脏", "宫": "子宫", "卵": "卵巢", "膀": "膀胱"}
    _organ_count = sum(1 for o in _all_organs if o in A)
    _organ_count += sum(1 for s, full in _all_organs_short.items() if s in A and full not in A)
    # "双肾"算一个器官，不触发多器官
    if "肾" in A: _organ_count = max(_organ_count, 1)
    if _organ_count >= 3 and method in ("converted_fill", "template_fill", "llm_free") and not _route_result["is_multi"]:
        logging.info(f"多器官兜底触发: organ_count={_organ_count} method={method}")
        report_llm = await asyncio.to_thread(_llm_multi_organ_fill, A, req.exam_type)
        if report_llm and report_llm.get("study_see"):
            report = report_llm
            report = _wrap_hints_with_toggle(report)
            method = "llm_multi"
            best_name = "多器官综合报告"
            warnings.append(f"多器官({_organ_count}个)自动切换综合报告")

    # Save
    report_id = None
    pid = None
    if req.patient_id and req.patient_id.strip():
        try:
            pid = int(req.patient_id)
            r = db.report_create(pid, match_template(req.exam_type), req.text, _filter_checked(report))
            report_id = r["id"] if r else None
        except Exception as e:
            logging.warning(f"报告保存失败: {e}")

    elapsed_ms = int((_time.time() - t0) * 1000)
    _save_trace_simple(req, pid, A, report, best_name, method, elapsed_ms, warnings)

    # 同步写入 api_reports 存档表（供外部系统拉取）
    _save_api_report(req, A, report, best_name)

    return _make_response(report, req, method, best_name, 0.85, warnings, A)
