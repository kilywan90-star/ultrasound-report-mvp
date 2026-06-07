"""
超声语音报告系统 - LLM增强引擎
使用 DeepSeek API 对ASR识别结果做理解+纠错+补全
"""
import json, os, re, urllib.request, time

# DeepSeek API 配置
LLM_API_KEY = "sk-43ffc7dafcec4369a039436377694820"
LLM_MODEL = "deepseek-v4-flash"
LLM_URL = "https://api.deepseek.com/chat/completions"

# 系统提示词（告诉LLM如何理解超声语音）
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


def llm_enhance(voice_text: str, retries=2) -> dict:
    """
    用LLM理解语音文本，输出结构化信息
    返回: {"sites":[], "description":"", "diagnosis":"", "is_normal":false}
    """
    if not voice_text or len(voice_text.strip()) < 3:
        return {"sites": [], "description": voice_text or "", "diagnosis": "", "is_normal": False}

    payload = {
        "model": LLM_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": voice_text}
        ],
        "response_format": {"type": "json_object"},
        "max_tokens": 800,
        "temperature": 0.1,
    }

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
            r = urllib.request.urlopen(req, timeout=30)
            result = json.loads(r.read())
            content = result["choices"][0]["message"]["content"]
            parsed = json.loads(content)

            if isinstance(parsed, dict):
                return {
                    "sites": parsed.get("sites", parsed.get("exam_site", [])),
                    "description": parsed.get("description", ""),
                    "diagnosis": parsed.get("diagnosis", ""),
                    "is_normal": parsed.get("is_normal", False),
                    "raw_llm_output": parsed,
                    "tokens_used": result.get("usage", {}).get("total_tokens", 0),
                }
        except json.JSONDecodeError:
            continue
        except Exception as e:
            if attempt < retries - 1:
                time.sleep(1)
                continue
            return {"sites": [], "description": voice_text, "diagnosis": "", "is_normal": False, "error": str(e)}

    return {"sites": [], "description": voice_text, "diagnosis": "", "is_normal": False}


def llm_match_template(voice_text: str, templates_list: list) -> dict:
    """
    LLM辅助模板匹配：从候选模板中选择最匹配的
    返回: {"template_name": "", "template_id": "", "confidence": 0}
    """
    # 准备候选模板列表（取前20个）
    candidates = [{"id": t.get("id", ""), "name": t.get("name", ""), "site": t.get("site", "")}
                  for t in templates_list[:30]]

    prompt = f"""根据语音文本，从以下模板中选择最匹配的一个。

语音文本: "{voice_text}"

可选模板:
{json.dumps(candidates, ensure_ascii=False)[:2000]}

输出JSON: {{"template_name": "选中的模板名", "template_id": "id", "confidence": 0-1评分, "reason": "选择理由"}}"""

    payload = {
        "model": LLM_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "response_format": {"type": "json_object"},
        "max_tokens": 300,
        "temperature": 0.1,
    }

    try:
        req = urllib.request.Request(
            LLM_URL,
            data=json.dumps(payload).encode(),
            headers={"Authorization": f"Bearer {LLM_API_KEY}", "Content-Type": "application/json"},
            method="POST"
        )
        r = urllib.request.urlopen(req, timeout=30)
        result = json.loads(r.read())
        content = result["choices"][0]["message"]["content"]
        return json.loads(content)
    except:
        return {"template_name": "", "template_id": "", "confidence": 0}
