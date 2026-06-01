"""DeepSeek 结构化提取 — 所见/提示双层输出 + 正式模板匹配锚定"""

import json
import os
import re
from openai import OpenAI
from openai import APIError, APITimeoutError

from templates import match_template as match_tpl_key, TEMPLATES
from template_loader import (
    match_template as match_formal_template,
    match_templates_multi,
    format_template_for_prompt,
    load_templates,
)

MAX_RETRIES = 2

# ICD-10 编码表
ICD10_MAP = {
    "K76.0": "脂肪肝", "K74.6": "肝硬化", "K80.0": "胆囊结石伴急性胆囊炎",
    "K80.1": "胆囊结石伴慢性胆囊炎", "K80.2": "胆囊结石", "K80.3": "胆管结石",
    "K80.5": "胆总管结石", "K81.0": "急性胆囊炎", "K81.1": "慢性胆囊炎",
    "K85.9": "急性胰腺炎", "K35.9": "急性阑尾炎", "K40.9": "腹股沟疝",
    "K82.8": "胆囊息肉", "Q44.6": "肝囊肿", "Q44.7": "多囊肝",
    "D18.0": "肝血管瘤", "C22.9": "肝癌", "N28.1": "肾囊肿",
    "N20.0": "肾结石", "N20.9": "泌尿系结石", "N13.3": "肾积水",
    "N40": "前列腺增生", "N40.0": "前列腺增生", "C64": "肾细胞癌",
    "D30.0": "肾错构瘤", "Q61.2": "多囊肾", "N18.9": "慢性肾病",
    "C67.9": "膀胱肿瘤", "D25.9": "子宫肌瘤", "D25.0": "子宫粘膜下肌瘤",
    "N80.0": "子宫腺肌症", "N84.0": "子宫内膜息肉", "N83.2": "卵巢囊肿",
    "D27.9": "卵巢畸胎瘤", "N70.1": "输卵管积水", "O20.9": "妊娠期出血",
    "O34.2": "子宫切口憩室", "O44.0": "胎盘低置", "O00.9": "异位妊娠",
    "O01.9": "葡萄胎", "O44.9": "前置胎盘", "O45.9": "胎盘早剥",
    "I05.0": "二尖瓣狭窄", "I34.0": "二尖瓣关闭不全", "I34.1": "二尖瓣脱垂",
    "I35.0": "主动脉瓣狭窄", "I35.1": "主动脉瓣关闭不全",
    "I07.1": "三尖瓣关闭不全", "I42.0": "扩张型心肌病",
    "I42.1": "肥厚型心肌病", "I25.1": "冠心病",
    "I50.9": "心力衰竭", "I31.3": "心包积液", "I27.0": "肺动脉高压",
    "I71.9": "主动脉瘤", "I71.4": "腹主动脉瘤",
    "Q21.0": "室间隔缺损", "Q21.1": "房间隔缺损", "Q25.0": "动脉导管未闭",
    "Q21.3": "法洛四联症", "D15.1": "左心房粘液瘤",
    "I70.0": "动脉粥样硬化", "I65.2": "颈动脉狭窄", "I74.3": "下肢动脉闭塞",
    "I80.2": "深静脉血栓", "E05.0": "甲亢", "E04.1": "甲状腺结节",
    "C73": "甲状腺癌", "N60.9": "乳腺纤维腺瘤", "N60.1": "乳腺增生",
    "C50.9": "乳腺癌", "R16.1": "脾大", "R18": "腹水",
    "R59.9": "淋巴结肿大", "Q89.2": "甲状舌管囊肿", "E21.0": "甲状旁腺腺瘤",
    "R33": "尿潴留", "K11.2": "腮腺炎", "C62.9": "睾丸肿瘤",
    "C54.9": "子宫体癌", "C56": "卵巢癌", "E06.3": "桥本氏甲状腺炎",
    "I51.7": "心脏扩大", "I51.8": "其他心脏疾病", "I33.0": "感染性心内膜炎",
    "I30.1": "缩窄性心包炎", "I81": "门静脉血栓", "I83.9": "下肢静脉曲张",
}

# 确保模板已加载
load_templates()


def _get_client():
    return OpenAI(
        api_key=os.getenv("DEEPSEEK_API_KEY"),
        base_url="https://api.deepseek.com/v1",
    )


def _system_prompt(exam_type: str, formal_tpl: dict | None = None) -> str:
    tpl_key = match_tpl_key(exam_type)
    tpl = TEMPLATES.get(tpl_key, TEMPLATES["abdomen"])

    # 正式模板参考
    formal_ref = ""
    if formal_tpl:
        formal_ref = f"""
## 正式模板参考（请按此格式输出）

{format_template_for_prompt(formal_tpl)}
"""

    return f"""你是一位资深超声科主任医师。将口语化的超声检查口述转换为规范化超声报告。

当前检查类型: {tpl["name"]}
覆盖脏器: {"、".join(tpl["organs"])}
{formal_ref}
## 规则
1. 口述中缺失的测量值填"___mm"占位，绝不编造数值
2. 口语转标准术语（"肝有点大"→"肝脏形态饱满"，"胆囊没有"→"胆囊未见异常"）
3. study_see 按脏器分段，每段格式: "脏器名: 描述。"
4. study_hint 每条一行，按临床重要性排序
5. study_hint 标注 ICD-10（格式 "K76.0 脂肪肝"）
6. 口述中提及的每一个脏器都在 study_see 中出现（包括正常脏器）
7. patient_info 全部填 null
8. 只输出 JSON

## 输出 JSON Schema
{{
  "patient_info": {{ "name": null, "gender": null, "age": null, "exam_id": null }},
  "exam_info": {{ "modality": "{tpl["name"]}", "device": null, "exam_date": null }},
  "study_see": "脏器分段描述的完整所见文本。每段格式: 脏器名: 描述。\\n例如: 肝脏: 形态大小正常，实质回声均匀。\\n胆囊: 大小正常，囊壁光滑，腔内未见异常回声。",
  "study_hint": [
    {{ "rank": 1, "diagnosis": "疾病名", "icd10": "K76.0 脂肪肝" }}
  ],
  "recommendation": "建议文字"
}}"""


def _extract_json(content: str) -> str:
    content = content.strip()
    m = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", content, re.DOTALL)
    if m:
        return m.group(1).strip()
    start = content.find("{")
    end = content.rfind("}")
    if start != -1 and end != -1 and end > start:
        return content[start: end + 1]
    return content


def _parse_json(content: str) -> dict:
    json_str = _extract_json(content)
    errors = []

    try:
        return json.loads(json_str)
    except json.JSONDecodeError as e:
        errors.append(f"直接解析: {e}")

    try:
        fixed = json_str.rstrip()
        open_braces = fixed.count("{") - fixed.count("}")
        open_brackets = fixed.count("[") - fixed.count("]")
        in_string = fixed.count('"') % 2 != 0
        if in_string:
            fixed += '"'
        fixed += "]" * open_brackets + "}" * open_braces
        return json.loads(fixed)
    except json.JSONDecodeError as e:
        errors.append(f"补全括号: {e}")

    lines = json_str.split("\n")
    for cut in range(1, min(5, len(lines))):
        try:
            return _parse_json("\n".join(lines[:-cut]))
        except Exception:
            pass

    raise ValueError(f"JSON 解析失败: {'; '.join(errors)}")


def _enrich_icd10(report: dict) -> dict:
    for imp in report.get("study_hint", []):
        icd10 = imp.get("icd10", "") or ""
        if not icd10.strip():
            continue
        code_only = icd10.strip().split()[0]
        name = ICD10_MAP.get(code_only, "")
        if name and name not in icd10:
            imp["icd10"] = f"{code_only} {name}"
    return report


def structure_report(raw_text: str, exam_type: str = "腹部超声") -> dict:
    """结构化提取：输出 study_see + study_hint 双层格式"""
    client = _get_client()

    # P0-2: 匹配正式模板
    formal_tpl = match_formal_template(raw_text, exam_type)

    last_error = None
    for attempt in range(MAX_RETRIES + 1):
        try:
            response = client.chat.completions.create(
                model="deepseek-v4-flash",
                messages=[
                    {"role": "system", "content": _system_prompt(exam_type, formal_tpl)},
                    {"role": "user", "content": (
                        f"请将以下{exam_type}检查口述转换为规范化超声报告"
                        f"（注意：study_see 必须包含口述中提到的每一个脏器）：\n\n{raw_text}"
                    )},
                ],
                temperature=0.1,
                max_tokens=4096,
            )
            content = response.choices[0].message.content
            if not content:
                raise RuntimeError("DeepSeek 返回空内容")

            report = _parse_json(content)
            report = _enrich_icd10(report)
            return report

        except (APIError, APITimeoutError) as e:
            last_error = e
            if attempt < MAX_RETRIES:
                import time
                time.sleep(1.5 ** attempt)
                continue
            raise RuntimeError(f"DeepSeek API 调用失败(已重试{MAX_RETRIES}次): {e}") from e

        except (json.JSONDecodeError, ValueError) as e:
            raise RuntimeError(f"结构化输出解析失败: {e}") from e

    raise RuntimeError(f"结构化失败: {last_error}")
