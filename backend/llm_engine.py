"""
超声语音报告系统 - LLM增强引擎 v2
使用 DeepSeek API 做语义理解、文本规范化、模板匹配和报告填充

核心功能:
1. llm_normalize: 乱序/混淆文本 → 规范化医学描述
2. llm_match_template: 理解语义后选择最匹配模板
3. llm_fill_template: 根据输入内容填充模板变量
"""
import json, os, re, urllib.request, time

LLM_API_KEY = "sk-43ffc7dafcec4369a039436377694820"
LLM_MODEL = "deepseek-v4-flash"
LLM_URL = "https://api.deepseek.com/chat/completions"

SYSTEM_PROMPT = """你是超声科医生助手。你的任务是根据语音识别文本，输出结构化JSON报告。

规则：
1. sites: 检查部位列表（如["肝脏","胆囊","脾脏"]）
2. description: 超声描述，用专业医学语言（补全口语缺失部分但不虚构）
3. diagnosis: 诊断结论（如果有）
4. is_normal: 是否正常（true/false）

语音文本特点：
- 医生只说异常部分（如"肝上有个囊肿"），正常器官不会提
- 口语化、可能有ASR识别错误
- 可能混有环境噪声词

输出要求：
- 只输出JSON，不要其他文字
- 描述要专业、简洁
- 不虚构未提及的内容"""

NORMALIZE_SYSTEM_PROMPT = """你是一位超声科医生。以下是一段文字顺序被打乱的超声描述。
你需要做的是：把打乱的汉字重新排列成通顺的超声医学描述。
保持所有数字和单位不变。
只输出整理后的文字，不要解释。

关键规则：
1. 超声描述的标准顺序是：器官名 + 形态/大小 + 表面/包膜 + 内部回声 + 其他发现
2. 常见的超声短语如"实质回声均匀"、"大小正常"、"形态规则"、"表面光滑"等可能会被打散
3. 只重新排列已有文字，不添加新内容，不删除内容
4. 数值如"4.8x1.8mm"、"12mm"等保持原样
5. 如果文字太少无法还原，直接原样输出

示例：
输入: "质回实音均大匀小正常"
输出: "实质回声均匀，大小正常"

输入: "回声均实质匀大常小正"
输出: "实质回声均匀，大小正常"

输入: "甲囊肿壮线有"
输出: "甲状腺有囊肿"

输入: "干脏大小正常回生军匀"
输出: "肝脏大小正常回声均匀"

输入: "肝内可见无回声区大小约" (正常顺序)
输出: "肝内可见无回声区大小约"

输入: "内胆可见囊结石"
输出: "胆囊内可见结石"""

MATCH_SYSTEM_PROMPT = """你是超声科医生助手。根据医生的语音描述，从候选模板列表中选择最匹配的一个。

规则：
- 仔细理解语音描述的医学含义，不要只看关键词
- 如果描述提到"未见异常"、"正常"，优先选正常模板
- 甲状腺、乳腺、心脏等专有部位的描述不要跨部位匹配
- 输出JSON格式：{"template_name": "选中的模板名（必须完全匹配候选列表中的名称）", "confidence": 0-1评分, "reason": "选择理由"}"""

FILL_SYSTEM_PROMPT = """你是超声科医生助手。根据医生提供的描述内容，填充超声报告模板中缺失的部分。

规则：
- 模板中的xx、x mm等占位符需要用输入中的实际数值替换
- 数值单位保持一致
- 只填充模板中明确占位的部分
- 保持模板原有的句子结构和医学用语
- 输出填充后的完整模板文本"""


def _call_deepseek(messages, system_prompt, response_format=None, max_tokens=1000, temperature=0.1, retries=2):
    """通用DeepSeek API调用"""
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
                LLM_URL,
                data=json.dumps(payload).encode(),
                headers={
                    "Authorization": f"Bearer {LLM_API_KEY}",
                    "Content-Type": "application/json"
                },
                method="POST"
            )
            r = urllib.request.urlopen(req, timeout=60)
            result = json.loads(r.read())
            content = result["choices"][0]["message"]["content"]
            tokens_used = result.get("usage", {}).get("total_tokens", 0)
            return content, tokens_used
        except json.JSONDecodeError:
            continue
        except Exception as e:
            if attempt < retries - 1:
                time.sleep(1)
                continue
            return None, 0
    return None, 0


def llm_normalize(scrambled_text: str) -> str:
    """
    LLM语义规范化: 乱序/混淆文本 → 通顺医学描述

    示例:
        "回声均实质匀大常小正" → "肝脏大小正常，实质回声均匀"
        "甲壮线结有节" → "甲状腺有结节"
    """
    if not scrambled_text or len(scrambled_text.strip()) < 3:
        return scrambled_text or ""

    content, tokens_used = _call_deepseek(
        messages=[{"role": "user", "content": scrambled_text}],
        system_prompt=NORMALIZE_SYSTEM_PROMPT,
        max_tokens=500,
        temperature=0.05,
    )
    if content:
        return content.strip()
    return scrambled_text


def llm_match_template(voice_text: str, candidates: list) -> dict:
    """
    LLM理解语义后选择最匹配的模板

    Args:
        voice_text: 医生语音/输入文本（可能乱序）
        candidates: 候选模板列表 [{"id": ..., "name": ..., "site": ..., "description": ...}]

    Returns:
        {"template_name": "...", "confidence": 0-1, "reason": "..."}
    """
    if not voice_text or not candidates:
        return {"template_name": "", "confidence": 0, "reason": "无候选"}

    # 候选模板信息精简（取前20个候选）
    candidate_info = []
    for t in candidates[:20]:
        candidate_info.append({
            "id": t.get("template_id", t.get("id", "")),
            "name": t.get("template_name", t.get("name", "")),
            "site": t.get("site", ""),
            "desc_summary": (t.get("description", "") or "")[:80]
        })

    prompt = f"""根据输入的超声描述文本，从以下候选模板中选择最匹配的一个。

输入文本: "{voice_text}"

候选模板:
{json.dumps(candidate_info, ensure_ascii=False)}

输出JSON: {{"template_name": "选中的模板名(必须完全匹配)", "confidence": 0-1评分, "reason": "选择理由"}}"""

    content, _ = _call_deepseek(
        messages=[{"role": "user", "content": prompt}],
        system_prompt=MATCH_SYSTEM_PROMPT,
        response_format={"type": "json_object"},
        max_tokens=500,
        temperature=0.1,
    )
    if content:
        try:
            result = json.loads(content)
            # 验证结果中的模板名在候选列表中
            matched_name = result.get("template_name", "")
            if matched_name:
                # 确保模板名匹配候选列表中的一个
                valid_names = {t.get("template_name", t.get("name", "")) for t in candidates[:20]}
                if matched_name not in valid_names:
                    # 尝试模糊匹配
                    for vn in valid_names:
                        if matched_name in vn or vn in matched_name:
                            result["template_name"] = vn
                            break
                    else:
                        result["confidence"] = 0
            return result
        except:
            pass
    return {"template_name": "", "confidence": 0, "reason": "LLM调用失败"}


def llm_fill_template(template_desc: str, input_text: str, template_name: str = "") -> str:
    """
    LLM根据输入内容填充模板中的占位变量

    Args:
        template_desc: 模板原文（含xx、x mm等占位符）
        input_text: 输入文本（含实际数值）
        template_name: 模板名（上下文参考）

    Returns:
        填充后的文本
    """
    if not template_desc or not input_text:
        return template_desc or ""

    prompt = f"""模板名称: {template_name or '未知'}
模板原文: {template_desc}

输入描述: {input_text}

请将模板中的占位符（xx、x mm等）替换为输入描述中的实际数值。
只替换明确的数值占位，不要修改其他文字。
输出填充后的完整模板。"""

    content, _ = _call_deepseek(
        messages=[{"role": "user", "content": prompt}],
        system_prompt=FILL_SYSTEM_PROMPT,
        max_tokens=1000,
        temperature=0.1,
    )
    if content:
        return content.strip()
    return template_desc


def llm_enhance(voice_text: str, retries=2) -> dict:
    """(保留原接口) LLM理解语音文本，输出结构化信息"""
    if not voice_text or len(voice_text.strip()) < 3:
        return {"sites": [], "description": voice_text or "", "diagnosis": "", "is_normal": False}

    content, _ = _call_deepseek(
        messages=[{"role": "user", "content": voice_text}],
        system_prompt=SYSTEM_PROMPT,
        response_format={"type": "json_object"},
        max_tokens=800,
        temperature=0.1,
        retries=retries,
    )
    if content:
        try:
            parsed = json.loads(content)
            if isinstance(parsed, dict):
                return {
                    "sites": parsed.get("sites", parsed.get("exam_site", [])),
                    "description": parsed.get("description", ""),
                    "diagnosis": parsed.get("diagnosis", ""),
                    "is_normal": parsed.get("is_normal", False),
                    "raw_llm_output": parsed,
                }
        except:
            pass
    return {"sites": [], "description": voice_text, "diagnosis": "", "is_normal": False}
