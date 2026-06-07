"""
超声语音报告系统 - LLM增强引擎 v2.1
使用 DeepSeek API + 输入缓存 做语义理解,文本规范化,匹配和填充

核心优化:
1. 输入缓存: 相同输入跳过API调用
2. 合并API: analyze_and_match 一次完成规范化+匹配+诊断
"""
import json, os, re, urllib.request, time, hashlib

LLM_API_KEY = "sk-43ffc7dafcec4369a039436377694820"
LLM_MODEL = "deepseek-v4-flash"
LLM_URL = "https://api.deepseek.com/chat/completions"

_cache = {}
_CACHE_MAX = 200

def _cache_key(text, prefix=''):
    return prefix + hashlib.sha256(text.encode('utf-8')).hexdigest()[:24]

def _cache_get(key):
    return _cache.get(key)

def _cache_set(key, value):
    if len(_cache) > _CACHE_MAX:
        keys = list(_cache.keys())
        for k in keys[:len(keys)//2]:
            del _cache[k]
    _cache[key] = value

SYSTEM_PROMPT = "你是超声科医生助手。根据语音识别文本,输出结构化JSON。sites:检查部位列表,description:超声描述,diagnosis:诊断,is_normal:是否正常。"

NORMALIZE_SYSTEM_PROMPT = "你是一位超声科医生。将打乱的汉字重新排列成通顺的超声医学描述。只输出整理后的文字。超声描述标准顺序:器官名->形态/大小->表面/包膜->内部回声->其他。只重新排列已有文字不添加不删除。"

MATCH_SYSTEM_PROMPT = "你是超声科医生助手。根据语音描述从候选模板选择最匹配的一个。输出JSON:模板名,confidence,理由。"

FILL_SYSTEM_PROMPT = "你是超声科医生助手。根据描述内容填充超声报告模板中缺失的部分。将xx,x mm等占位符替换为实际数值。输出填充后完整模板。"

DIAGNOSIS_SYSTEM_PROMPT = "你是超声科医生助手。根据超声描述生成规范的诊断结论。简洁专业。输出纯文本。"

ANALYZE_SYSTEM_PROMPT = "你是超声科医生助手。根据输入文本完成:1.文字可能乱序或同音错字请还原通顺;2.从候选模板选最匹配的;3.判断诊断。输出JSON:normalized_text,template_name,diagnosis,confidence,reason。"


def _call_deepseek(messages, system_prompt, response_format=None, max_tokens=1000, temperature=0.1, retries=2):
    payload = {
        "model": LLM_MODEL,
        "messages": [{"role": "system", "content": system_prompt}] + messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    if response_format:
        payload["response_format"] = response_format
    for attempt in range(retries):
        try:
            req = urllib.request.Request(
                LLM_URL, data=json.dumps(payload).encode(),
                headers={"Authorization": "Bearer " + LLM_API_KEY, "Content-Type": "application/json"},
                method="POST"
            )
            r = urllib.request.urlopen(req, timeout=60)
            result = json.loads(r.read())
            content = result["choices"][0]["message"]["content"]
            return content, result.get("usage", {}).get("total_tokens", 0)
        except:
            if attempt < retries - 1:
                time.sleep(1)
                continue
            return None, 0
    return None, 0


def llm_analyze_and_match(scrambled_text, candidates):
    if not scrambled_text or not candidates:
        return {"normalized_text": scrambled_text or "", "template_name": "", "diagnosis": "", "confidence": 0}
    ck = _cache_key(scrambled_text, 'analyze')
    cached = _cache_get(ck)
    if cached:
        return cached
    candidate_info = [{"name": t.get("name") or t.get("template_name", ""), "id": t.get("id") or t.get("template_id", ""), "site": t.get("site", ""), "summary": (t.get("description", "") or "")[:60]} for t in candidates[:15]]
    prompt = ("输入文本: " + scrambled_text + "\n候选模板: " + json.dumps(candidate_info, ensure_ascii=False) +
              "\n输出JSON: {\"normalized_text\":\"还原的通顺描述\",\"template_name\":\"完全匹配的模板名\",\"diagnosis\":\"诊断\",\"confidence\":0-1,\"reason\":\"理由\"}")
    content, _ = _call_deepseek(
        messages=[{"role": "user", "content": prompt}],
        system_prompt=ANALYZE_SYSTEM_PROMPT,
        response_format={"type": "json_object"},
        max_tokens=800, temperature=0.05,
    )
    if content:
        try:
            result = json.loads(content)
            matched_name = result.get("template_name", "")
            valid_names = {t.get("name") or t.get("template_name", "") for t in candidates}
            if matched_name and matched_name not in valid_names:
                for vn in valid_names:
                    if matched_name in vn or vn in matched_name:
                        result["template_name"] = vn
                        break
                else:
                    result["confidence"] = 0
            _cache_set(ck, result)
            return result
        except:
            pass
    result = {"normalized_text": scrambled_text, "template_name": "", "diagnosis": "", "confidence": 0}
    _cache_set(ck, result)
    return result


def llm_fill_template(template_desc, input_text, template_name=""):
    if not template_desc or not input_text:
        return template_desc or ""
    fill_key = _cache_key(template_desc + '|' + input_text, 'fill')
    cached = _cache_get(fill_key)
    if cached:
        return cached
    prompt = ("模板: " + (template_name or "未知") + "\n原文: " + template_desc +
              "\n输入: " + input_text + "\n将模板中xx,x mm等占位符替换为实际数值。输出完整模板。")
    content, _ = _call_deepseek(
        messages=[{"role": "user", "content": prompt}],
        system_prompt=FILL_SYSTEM_PROMPT,
        max_tokens=1000, temperature=0.1,
    )
    result = content.strip() if content else template_desc
    _cache_set(fill_key, result)
    return result


def llm_normalize(scrambled_text):
    if not scrambled_text or len(scrambled_text.strip()) < 3:
        return scrambled_text or ""
    ck = _cache_key(scrambled_text, 'norm')
    cached = _cache_get(ck)
    if cached:
        return cached
    content, _ = _call_deepseek(
        messages=[{"role": "user", "content": scrambled_text}],
        system_prompt=NORMALIZE_SYSTEM_PROMPT,
        max_tokens=500, temperature=0.05,
    )
    result = content.strip() if content else scrambled_text
    _cache_set(ck, result)
    return result


def llm_match_template(voice_text, candidates):
    if not voice_text or not candidates:
        return {"template_name": "", "confidence": 0, "reason": "no candidates"}
    ck = _cache_key(voice_text + str(len(candidates)), 'match')
    cached = _cache_get(ck)
    if cached:
        return cached
    candidate_info = [{"id": t.get("id", t.get("template_id", "")), "name": t.get("name", t.get("template_name", "")), "site": t.get("site", ""), "summary": (t.get("description", "") or "")[:60]} for t in candidates[:20]]
    prompt = ("输入: " + voice_text + "\n候选: " + json.dumps(candidate_info, ensure_ascii=False) +
              "\n输出JSON: {\"template_name\":\"选中模板名\",\"confidence\":0-1,\"reason\":\"理由\"}")
    content, _ = _call_deepseek(
        messages=[{"role": "user", "content": prompt}],
        system_prompt=MATCH_SYSTEM_PROMPT,
        response_format={"type": "json_object"},
        max_tokens=500, temperature=0.1,
    )
    result = {"template_name": "", "confidence": 0, "reason": "LLM call failed"}
    if content:
        try:
            result = json.loads(content)
            matched_name = result.get("template_name", "")
            if matched_name:
                valid_names = {t.get("name", t.get("template_name", "")) for t in candidates[:20]}
                if matched_name not in valid_names:
                    for vn in valid_names:
                        if matched_name in vn or vn in matched_name:
                            result["template_name"] = vn
                            break
                    else:
                        result["confidence"] = 0
        except:
            pass
    _cache_set(ck, result)
    return result


def llm_generate_diagnosis(description, template_name=""):
    if not description:
        return ""
    ck = _cache_key(description + '|' + template_name, 'diag')
    cached = _cache_get(ck)
    if cached:
        return cached
    context = ("模板: " + template_name + "\n描述: " + description) if template_name else ("描述: " + description)
    content, _ = _call_deepseek(
        messages=[{"role": "user", "content": context}],
        system_prompt=DIAGNOSIS_SYSTEM_PROMPT,
        max_tokens=300, temperature=0.1,
    )
    result = content.strip() if content else ""
    _cache_set(ck, result)
    return result


def llm_enhance(voice_text, retries=2):
    if not voice_text or len(voice_text.strip()) < 3:
        return {"sites": [], "description": voice_text or "", "diagnosis": "", "is_normal": False}
    ck = _cache_key(voice_text, 'enhance')
    cached = _cache_get(ck)
    if cached:
        return cached
    content, _ = _call_deepseek(
        messages=[{"role": "user", "content": voice_text}],
        system_prompt=SYSTEM_PROMPT,
        response_format={"type": "json_object"},
        max_tokens=800, temperature=0.1, retries=retries,
    )
    result = {"sites": [], "description": voice_text, "diagnosis": "", "is_normal": False}
    if content:
        try:
            parsed = json.loads(content)
            if isinstance(parsed, dict):
                result = {"sites": parsed.get("sites", parsed.get("exam_site", [])), "description": parsed.get("description", ""), "diagnosis": parsed.get("diagnosis", ""), "is_normal": parsed.get("is_normal", False), "raw_llm_output": parsed}
        except:
            pass
    _cache_set(ck, result)
    return result
