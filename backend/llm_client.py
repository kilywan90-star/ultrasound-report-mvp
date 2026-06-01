"""DeepSeek 结构化提取 — 通过 DeepSeek 官方 API"""

import json
import os
import re
from openai import OpenAI
from openai import APIError, APITimeoutError

from templates import match_template, template_prompt, TEMPLATES

MAX_RETRIES = 2

# 超声常见 ICD-10 编码表（编码 → 疾病名称）
ICD10_MAP = {
    # 腹部/消化
    "K76.0": "脂肪肝", "K74.6": "肝硬化", "K80.0": "胆囊结石伴急性胆囊炎",
    "K80.1": "胆囊结石伴慢性胆囊炎", "K80.2": "胆囊结石", "K80.3": "胆管结石",
    "K80.5": "胆总管结石", "K81.0": "急性胆囊炎", "K81.1": "慢性胆囊炎",
    "K81.9": "胆囊炎", "K85.9": "急性胰腺炎", "K86.1": "慢性胰腺炎",
    "K35.9": "急性阑尾炎", "K40.9": "腹股沟疝", "K56.1": "肠套叠",
    "K82.8": "胆囊息肉", "Q44.6": "肝囊肿", "Q44.7": "多囊肝",
    # 肝脏
    "D18.0": "肝血管瘤", "C22.9": "肝癌", "D13.4": "肝腺瘤",
    # 泌尿
    "N28.1": "肾囊肿", "N20.0": "肾结石", "N20.9": "泌尿系结石",
    "N13.3": "肾积水", "N40": "前列腺增生", "N40.0": "前列腺增生",
    "C64": "肾细胞癌", "D30.0": "肾错构瘤", "Q61.2": "多囊肾",
    "N18.9": "慢性肾病", "C67.9": "膀胱肿瘤",
    # 妇科
    "D25.9": "子宫肌瘤", "D25.0": "子宫粘膜下肌瘤", "N80.0": "子宫腺肌症",
    "N84.0": "子宫内膜息肉", "N83.2": "卵巢囊肿", "D27.9": "卵巢畸胎瘤",
    "N70.1": "输卵管积水", "N72": "宫颈肥大", "N92.0": "月经不调",
    "C56": "卵巢癌", "C54.9": "子宫体癌",
    # 产科
    "O20.9": "妊娠期出血", "O34.2": "子宫切口憩室", "O44.0": "胎盘低置",
    "O46.9": "产前出血", "O41.0": "羊水过少", "O41.9": "羊水过多",
    "O36.6": "巨大儿", "O00.9": "异位妊娠", "O01.9": "葡萄胎",
    "O44.9": "前置胎盘", "O45.9": "胎盘早剥",
    # 心脏
    "I05.0": "二尖瓣狭窄", "I34.0": "二尖瓣关闭不全", "I34.1": "二尖瓣脱垂",
    "I35.0": "主动脉瓣狭窄", "I35.1": "主动脉瓣关闭不全",
    "I07.1": "三尖瓣关闭不全", "I42.0": "扩张型心肌病",
    "I42.1": "肥厚型心肌病", "I25.1": "冠心病",
    "I21.9": "急性心肌梗死", "I50.9": "心力衰竭",
    "I31.3": "心包积液", "I27.0": "肺动脉高压",
    "I71.9": "主动脉瘤", "I71.4": "腹主动脉瘤",
    "Q21.0": "室间隔缺损", "Q21.1": "房间隔缺损", "Q25.0": "动脉导管未闭",
    "Q21.3": "法洛四联症", "D15.1": "左心房粘液瘤",
    "I33.0": "感染性心内膜炎", "I30.1": "缩窄性心包炎",
    "I81": "门静脉血栓", "I51.7": "心脏扩大", "I51.8": "其他心脏疾病",
    # 血管
    "I70.0": "动脉粥样硬化", "I65.2": "颈动脉狭窄", "I74.3": "下肢动脉闭塞",
    "I80.2": "深静脉血栓", "I83.9": "下肢静脉曲张",
    # 甲状腺
    "E05.0": "甲状腺功能亢进", "E03.9": "甲状腺功能减退",
    "E04.1": "甲状腺结节", "C73": "甲状腺癌",
    "E06.1": "亚急性甲状腺炎", "E06.3": "桥本氏甲状腺炎",
    # 乳腺
    "N60.9": "乳腺纤维腺瘤", "N60.1": "乳腺增生", "N60.0": "乳腺囊肿",
    "C50.9": "乳腺癌", "D24": "乳腺良性肿瘤",
    # 其他
    "R16.1": "脾大", "R18": "腹水", "R59.9": "淋巴结肿大",
    "Q89.2": "甲状舌管囊肿", "D44.6": "颈动脉体瘤", "E21.0": "甲状旁腺腺瘤",
    "R33": "尿潴留", "K11.2": "腮腺炎", "C62.9": "睾丸肿瘤",
    "R31": "血尿", "R10.4": "腹痛",
}


def _enrich_icd10(report: dict) -> dict:
    """给纯编码补上疾病名称"""
    for imp in report.get("impression", []):
        icd10 = imp.get("icd10", "")
        if not icd10 or icd10 == "null":
            continue
        # 如果已经有名称（含空格/中文），跳过
        code_only = icd10.strip().split()[0] if icd10.strip() else ""
        name = ICD10_MAP.get(code_only, "")
        if name and name not in icd10:
            imp["icd10"] = f"{code_only} {name}"
    return report


def _get_client():
    return OpenAI(
        api_key=os.getenv("DEEPSEEK_API_KEY"),
        base_url="https://api.deepseek.com/v1",
    )


def _system_prompt(exam_type: str) -> str:
    tpl_key = match_template(exam_type)
    tpl = TEMPLATES.get(tpl_key, TEMPLATES["abdomen"])
    field_desc = template_prompt(tpl_key)

    return f"""你是一位资深超声科主任医师。将口语化的超声检查口述转换为严格结构化的超声报告 JSON。

## 当前检查类型: {tpl["name"]}
## 覆盖脏器: {"、".join(tpl["organs"])}

## 规则
1. 口述中缺失的测量值或字段填写 null，绝不编造
2. 口语转换为标准术语（"肝有点大"→"肝脏增大"，"胆囊没有/没事/正常"→"胆囊未见异常"）
3. **每一个口述中提及的脏器都必须有一条 findings 记录，包括正常脏器。**
   - 例如医生说"胆囊未见异常"或"胆囊没有"，也必须输出 {{"organ": "胆囊", "size": "大小正常", "border": "光滑", ...}}，不可省略
   - 正常脏器的 impression 不要重复列入，impression 只列阳性发现
4. 如果所有脏器均未见异常，impression 应包含一条"{{检查类型}}未见明显异常"
5. impression 按临床重要性从高到低排序
6. 诊断使用标准疾病名称，标注 ICD-10 编码+名称（格式如 "K76.0 脂肪肝" 或 "I35.0 主动脉瓣狭窄"），如果不知道名称就只写编码
7. **患者信息 (patient_info) 全部填 null，不要从口述中提取任何患者姓名/性别/年龄。患者信息由系统录入。**
8. 只输出 JSON，不要任何解释性文字

## 输出 JSON Schema
{{
  "patient_info": {{ "name": "string|null", "gender": "男|女|null", "age": "integer|null", "exam_id": "string|null" }},
  "exam_info": {{ "modality": "{tpl['name']}", "device": "string|null", "exam_date": "string|null" }},
{field_desc},
  "impression": [{{ "rank": "integer", "diagnosis": "string", "icd10": "string|null" }}],
  "recommendation": "string|null"
}}"""


def _extract_json(content: str) -> str:
    """从 LLM 输出中健壮地提取 JSON 字符串"""
    content = content.strip()

    # 策略1: ```json ... ``` 或 ``` ... ```
    m = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", content, re.DOTALL)
    if m:
        return m.group(1).strip()

    # 策略2: 找到第一个 { 和最后一个 } 之间的内容
    start = content.find("{")
    end = content.rfind("}")
    if start != -1 and end != -1 and end > start:
        return content[start : end + 1]

    return content


def _parse_json(content: str) -> dict:
    """带容错的 JSON 解析"""
    json_str = _extract_json(content)
    errors = []

    # 尝试1: 直接解析
    try:
        return json.loads(json_str)
    except json.JSONDecodeError as e:
        errors.append(f"直接解析: {e}")

    # 尝试2: 修复尾部截断（补全缺失的 } ] "）
    try:
        fixed = json_str.rstrip()
        # 数括号
        open_braces = fixed.count("{") - fixed.count("}")
        open_brackets = fixed.count("[") - fixed.count("]")
        in_string = fixed.count('"') % 2 != 0
        if in_string:
            fixed += '"'
        fixed += "]" * open_brackets + "}" * open_braces
        return json.loads(fixed)
    except json.JSONDecodeError as e:
        errors.append(f"补全括号: {e}")

    # 尝试3: 逐行删除最后几行直到解析成功（处理中途截断）
    lines = json_str.split("\n")
    for cut in range(1, min(5, len(lines))):
        try:
            truncated = "\n".join(lines[:-cut])
            return _parse_json(truncated)  # 递归尝试补全
        except Exception:
            pass

    raise ValueError(f"JSON 解析失败，已尝试: {'; '.join(errors)}")


def structure_report(raw_text: str, exam_type: str = "腹部超声") -> dict:
    """将超声口述文本转换为结构化报告 JSON（带重试）"""
    client = _get_client()
    last_error = None

    for attempt in range(MAX_RETRIES + 1):
        try:
            response = client.chat.completions.create(
                model="deepseek-v4-flash",
                messages=[
                    {"role": "system", "content": _system_prompt(exam_type)},
                    {"role": "user", "content": (
                        f"请将以下{exam_type}检查口述转换为结构化报告"
                        f"（注意：口述中提到的每一个脏器，无论正常还是异常，都必须单独列出一条 finding，不可遗漏）"
                        f"：\n\n{raw_text}"
                    )},
                ],
                temperature=0.1,
                max_tokens=4096,
            )
            content = response.choices[0].message.content
            if not content:
                raise RuntimeError("DeepSeek 返回空内容")

            return _enrich_icd10(_parse_json(content))

        except (APIError, APITimeoutError) as e:
            last_error = e
            if attempt < MAX_RETRIES:
                # API 层错误（限流/超时），等待后重试
                import time
                time.sleep(1.5 ** attempt)
                continue
            raise RuntimeError(f"DeepSeek API 调用失败(已重试{MAX_RETRIES}次): {e}") from e

        except (json.JSONDecodeError, ValueError) as e:
            # JSON 解析失败，重试不会改变结果
            raise RuntimeError(f"结构化输出解析失败: {e}") from e

    raise RuntimeError(f"结构化失败: {last_error}")
