#!/usr/bin/env python3
"""
Phase 1: Template Anchoring Engine (D-Path)
意图检测→精确模板名→LLM仅填充变量

策略:
1. 利用 template_tags_v2.json 的363个标签 + 关键词匹配 → 选出top-3候选模板
2. 从超声模板CSV中提取完整 INFO1 模板文本
3. 解析 INFO1 中的 [变量] 和 [选项A;选项B] 格式
4. LLM deepseek-chat 仅做一件事: 从ASR文本中提取值填入变量
5. 输出: 完全填充的报告 + voice/unfill 颜色标记
"""

import json, csv, os, re, time, logging
from pathlib import Path
from openai import OpenAI
from collections import defaultdict

_log = logging.getLogger(__name__)

# ── Config ──
TAG_FILE = Path(__file__).parent / "knowledge" / "template_tags_v2.json"
CSV_FILE = Path(os.environ.get("TEMPLATE_CSV", ""))
RULE_FILE = Path(__file__).parent / "knowledge" / "master_rules.json"

# ── 1. 模板精确匹配 ──
_tag_index = None
_csv_index = None  # DISCNAME → row dict

def _load_tags():
    global _tag_index
    if _tag_index is not None:
        return _tag_index
    _tag_index = {"by_name": {}, "by_level2": defaultdict(list), "all_names": []}
    with open(TAG_FILE, encoding='utf-8') as f:
        data = json.load(f)
    for cat in data.get("categories", []):
        level2 = cat.get("level2", "")
        for tpl in cat.get("templates", []):
            name = tpl.get("name", "").strip().lstrip("*")
            if name:
                _tag_index["by_name"][name] = tpl
                _tag_index["by_level2"][level2].append(name)
                _tag_index["all_names"].append(name)
    return _tag_index


def _load_csv():
    global _csv_index
    if _csv_index is not None:
        return _csv_index
    _csv_index = {}
    with open(CSV_FILE, encoding='utf-8-sig') as f:
        for row in csv.DictReader(f):
            name = (row.get("DISCNAME") or "").strip()
            if name and name not in ("0", "NULL", ""):
                # Clean: remove prefix codes like "001 ", "002 " etc.
                clean = re.sub(r'^\d+\s+', '', name)
                _csv_index[name] = dict(row)
                if clean != name:
                    _csv_index[clean] = dict(row)
    return _csv_index


def match_exact_template(text: str, exam_type: str = "") -> list[dict]:
    """精确匹配模板名: 检查部位路由 + 363标签关键词打分, 返回top-5"""
    tags = _load_tags()

    # P-2: 检查部位路由 (新) — 根据口语词限定模板搜索范围
    body_part_scope = None
    try:
        with open(Path(__file__).parent / "knowledge" / "exam_part_routing.json", encoding='utf-8') as f:
            routing = json.load(f)
        for cat in routing.get("categories", []):
            # 先试方言映射
            dialect_ok = False
            for dialect, standard in cat.get("dialect_map", {}).items():
                if dialect in text:
                    text = text.replace(dialect, standard)
                    dialect_ok = True
            # 再试路由关键词
            for kw in cat.get("routing_keywords", []):
                if kw in text:
                    body_part_scope = cat.get("linked_template_level2")
                    break
            if body_part_scope:
                break
    except Exception:
        pass

    scored = {}

    # P-1: 湘普方言清洗 — P0评分前先纠正同音错别字
    _dialect = None
    try:
        with open(Path(__file__).parent / "knowledge" / "dialect_mapping.json", encoding='utf-8') as f:
            _dialect = json.load(f).get("mappings", {})
    except: pass
    if _dialect:
        cleaned = text
        for wrong, correct in _dialect.items():
            if wrong in cleaned:
                cleaned = cleaned.replace(wrong, correct)
        text = cleaned  # 用清洗后的文本做后续所有匹配

    # P0: 模板匹配关键词精确命中 (来自master_rules.json)
    match_kw = {}
    try:
        with open(RULE_FILE, encoding='utf-8') as f:
            rules = json.load(f)
        match_kw = rules.get("templates", {}).get("match_keywords", {})
    except: pass

    for tpl_name, keywords in match_kw.items():
        for kw in keywords:
            if kw in text and len(kw) >= 2:
                score = 300
                # 否定检测: 如果模板是疾病类型, 但文本用否定词描述 → 大幅扣分
                abnormal_in_name = ["结石","囊肿","肌瘤","息肉","癌","瘤","占位","积液"]
                if any(a in tpl_name for a in abnormal_in_name):
                    neg_kw = ["未见","没有","无","未探及","未发现","未检出","排除"]
                    for a in abnormal_in_name:
                        if a in tpl_name:
                            for n in neg_kw:
                                if f"{n}{a}" in text or f"{n} {a}" in text or f"{n}的{a}" in text:
                                    score = 50  # 强扣分: 否定描述不应匹配疾病模板
                                    break
                scored[tpl_name] = max(scored.get(tpl_name, 0), score)
                break

    # P1: 标签名关键词精确匹配 (限定在 body_part_scope 范围内)
    for name in tags["all_names"]:
        # 如果已有部位路由, 限制标签搜索范围
        if body_part_scope:
            # 根据 level2 过滤: 乳腺/浅表/腹部/泌尿/妇科/心脏/血管/产科
            tpl_info = tags.get("by_name", {}).get(name, {})
            tpl_level2 = tpl_info.get("level2", "")
            if tpl_level2 and tpl_level2 != body_part_scope:
                continue
        if name in text and len(name) >= 2:
            bonus = 200 + len(name) * 10
            # 疾病词有证据加分
            abnormal_kw = ["癌","瘤","结石","囊肿","息肉","增生","钙化","硬化"]
            if any(kw in name for kw in abnormal_kw):
                # 否定检测: 文本中含"没有/未见/无+疾病词" → 大幅扣分
                neg_kw = ["未见","没有","无","未探及","未发现","未检出"]
                has_negation = any(f"{n}{kw}" in text for n in neg_kw for kw in abnormal_kw if kw in name)
                if has_negation:
                    bonus -= 200  # 否定式描述 → 强扣分(不应匹配疾病模板)
                elif any(kw in text for kw in abnormal_kw):
                    bonus += 30  # 有证据加分
                else:
                    bonus -= 80  # 无证据扣分
            scored[name] = max(scored.get(name, 0), bonus)

    # P2: 器官+疾病组合匹配 (用 tags 的 level3)
    organ_words = ["肝脏","胆囊","胰腺","脾脏","肾脏","子宫","卵巢","胎儿",
                   "甲状腺","乳腺","前列腺","膀胱","心脏","颈动脉","椎动脉","大脑"]
    for name, tpl in tags["by_name"].items():
        level3 = tpl.get("level3", "")
        for organ in organ_words:
            if organ in text and organ in level3:
                scored[name] = scored.get(name, 0) + 40
                break

    # P3: 正常模式高分加成 + 异常模式扣分
    normal_patterns = ["正常","未见异常","未见明显异常","形态大小正常","回声均匀","未见"]
    has_normal = any(p in text for p in normal_patterns)
    has_abnormal = any(kw in text for kw in ["结石","囊肿","肌瘤","息肉","增生(?!样)","扩张(?![的])","积液","占位","团块","钙化","癌","瘤","硬化","积水","腹水","回声增粗","回声增强","回声改变","包块","肿物"])
    if has_normal and not has_abnormal:
        # 正常报告：遍历 scored 的所有 key（包括 match_kw 来的），强力推"正常"模板
        for name in list(scored.keys()):
            if "正常" in name or "未见异常" in name or "正常各器官" in name:
                scored[name] = scored.get(name, 0) + 200
            # 疾病模板大幅扣分
            name_clean = name.lstrip("*").replace(" ", "")
            abnormal_name_kw = ["结石","囊肿","肌瘤","息肉","癌","瘤","硬化","积水","钙化","增生","腹水","扩张","占位","异常"]
            if any(kw in name_clean for kw in abnormal_name_kw):
                scored[name] = scored.get(name, 0) - 150

    # P4: 检查类型匹配加分 + 模板名exam_type关键词匹配
    if exam_type:
        for name, tpl in tags["by_name"].items():
            level2 = tpl.get("level2", "")
            level1 = tpl.get("level1", "")
            if (level2 and level2 in exam_type) or (level1 and level1 in exam_type):
                scored[name] = scored.get(name, 0) + 50
            # exam_type关键词命中模板名 → 大幅加分(每个器官+60)
            exam_keywords = {"腹部":["肝","胆","胰","脾","肾","腹部","胃肠","胆囊","胆管","门静脉"],
                             "心脏":["心脏","二尖","三尖","主动脉","心包","瓣膜","EF","心室","心房","心肌","室壁"],
                             "妇产":["子宫","卵巢","宫颈","盆腔","胎儿","孕囊","胎盘","卵泡","内膜","妊娠","妇科","产科","附件","输卵管"],
                             "甲状腺":["甲状腺","峡部","TI-RAD","结节","叶","颌下","腺体","囊泡","囊肿"],
                             "乳腺":["乳腺","乳","BI-RAD","腋窝","象限","导管","囊肿","增生","结节","纤维腺瘤","囊泡"],
                             "血管":["颈动脉","椎动脉","斑块","IMT","动脉","静脉","血流速"],
                             "泌尿":["肾","输尿管","膀胱","前列腺","精囊","睾丸","附睾","残余尿","结石","积水","囊肿","增生","皮质","肾盂"]}
            for cat_kw, organ_list in exam_keywords.items():
                if cat_kw in exam_type:
                    for organ in organ_list:
                        if organ in name and len(organ) >= 2:
                            scored[name] = scored.get(name, 0) + 60
                            break

    # P5: 器官-异常词关联矩阵 (从真实报告中学习, 提高器官匹配精度)
    _organ_disease = None
    try:
        with open(Path(__file__).parent / "knowledge" / "organ_disease_matrix.json", encoding='utf-8') as f:
            _organ_disease = json.load(f).get("matrix", {})
    except: pass
    if _organ_disease:
        # 文本中出现的器官关键词
        text_organs = [o for o in ["肝脏","胆囊","胰腺","脾脏","肾脏","双肾","子宫","卵巢","甲状腺","乳腺","前列腺","膀胱","颈动脉","椎动脉","心脏","心包"] if o in text]
        for tpl_name in list(scored.keys()):
            for org in text_organs:
                if org in _organ_disease:
                    # 该器官最常见的top3异常词
                    top_diseases = list(_organ_disease[org].keys())[:3]
                    for d in top_diseases:
                        if d in text and d in tpl_name:
                            scored[tpl_name] = scored.get(tpl_name, 0) + 90  # 器官+疾病精准匹配
                            break
                # 反向: 模板名含该器官的最常见异常词 → 加分
                if org in tpl_name:
                    for d in list(_organ_disease.get(org, {}).keys())[:3]:
                        if d in text:
                            scored[tpl_name] = scored.get(tpl_name, 0) + 80
                            break

    # P6: 跨类型防护 (只在明显跨类型时才扣分, 如'妇产模板'在'腹部超声'下)
    if exam_type:
        _strong_cross = {
            "心脏超声": ["子宫","卵巢","前列腺","甲状腺","乳腺","颈动脉"],
            "妇产超声": ["颈动脉","前列腺","甲状腺","椎动脉","心包"],
            "血管超声": ["子宫","卵巢","胎儿","胎盘","二尖瓣","胆囊"],
            "甲状腺超声": ["子宫","胎盘","前列腺","胆囊","颈动脉"],
            "泌尿前列腺": ["子宫","卵巢","胎儿","甲状腺","乳腺","颈动脉"],
        }
        forbidden = _strong_cross.get(exam_type, [])
        if forbidden:
            for tpl_name in list(scored.keys()):
                for f in forbidden:
                    if f in tpl_name:
                        scored[tpl_name] = scored.get(tpl_name, 0) - 150
                        break

    # 归一化: score -> confidence_pct (0-100)
    results = []
    if scored:
        csv_data = _load_csv()
        results = []
        max_possible = max(scored.values()) if scored else 1  # P0(300) + P1(240) + P2(40) + P3(200) + P4(30)
        ranked = sorted(scored.items(), key=lambda x: -x[1])
        for name, score in ranked:
            # 分级映射: score->confidence_pct
            if score >= 350: confidence_pct = min(100, 90 + (score-350)//10)
            elif score >= 250: confidence_pct = min(89, 70 + (score-250)//5)
            elif score >= 150: confidence_pct = min(69, 50 + (score-150)//5)
            elif score >= 50: confidence_pct = min(49, 30 + (score-50)//2)
            else: confidence_pct = max(0, score)
            if score > 0:
                entry = {
                    "tpl_name": name, "score": score,
                    "confidence_pct": confidence_pct,
                    "info1": "", "module": "",
                }
                tpl_info = tags["by_name"].get(name, {})
                entry["level2"] = tpl_info.get("level2", "")
                entry["level3"] = tpl_info.get("level3", "")
                if name in csv_data:
                    entry["info1"] = csv_data[name].get("INFO1", "") or ""
                    entry["module"] = csv_data[name].get("MODULENAME", "") or ""
                results.append(entry)
            if len(results) >= 5:
                break

    return results


# ── 2. 模板变量解析 ──
def parse_template_variables(info1: str) -> dict:
    """解析模板中的 [变量] 和 [选项A;选项B] 格式"""
    # 提取所有 [xxx;yyy;zzz] 和 [xxx] 模式
    option_pattern = re.compile(r'\[([^\]]+)\]')
    options = []
    simple_vars = set()

    for m in option_pattern.finditer(info1):
        content = m.group(1)
        if ';' in content:
            parts = [p.strip() for p in content.split(';') if p.strip()]
            if len(parts) >= 2:
                options.append({"raw": m.group(0), "choices": parts, "span": m.span()})
        elif not content.startswith('_') and not content.strip() == '':
            # 简单的描述性文本 —— 值占位符
            # 检查是否包含测量值关键词
            if any(kw in content for kw in ["mm","cm","×","*","×", "Kg", "kg"]):
                simple_vars.add(content)

    # 将数字mm和cm模式也识别为变量
    num_vars = re.findall(r'\b\d+\.?\d*\s*(?:mm|cm|厘米|毫米)\b', info1)
    # 将 ___ 模式识别为待填变量
    blank_vars = re.findall(r'___+\s*(?:mm|cm)?', info1)

    return {
        "option_groups": options,
        "simple_vars": list(simple_vars),
        "num_placeholders": len(num_vars),
        "blank_placeholders": len(blank_vars),
        "total_variables": len(options) + len(simple_vars),
    }


# ── 3. LLM 精填引擎 ──
def _get_llm_client():
    return OpenAI(
        api_key=os.getenv("DEEPSEEK_API_KEY"),
        base_url="https://api.deepseek.com/v1",
    )


FILL_SYSTEM_PROMPT = """你是一位资深超声科主任医师。你的唯一任务是将超声口述中的测量值和描述填入模板。

## 核心规则
1. 只填入明确出现在口述中的值，绝不编造
2. 模板中的 [选项A;选项B;选项C] → 只保留口述中提到的那个
3. 模板中的 "mm" 处填入实际数值
4. 口述中缺失的填 "___mm" 保留占位
5. 保持模板的完整结构，只替换变量部分
6. 用 <b class="voice">值</b> 标记从口述中提取的数值
7. 最终报告只输出纯文本+HTML标记，不要添加任何JSON包装

## 输入格式
- 口述: 医生的超声口述原文
- 模板: 需要填充的超声报告模板(含[选项]和mm占位符)

## 输出格式
只输出填充后的完整报告文本，不要添加任何解释。"""


def llm_fill_template(asr_text: str, template: str, exam_type: str = "腹部超声") -> str:
    """LLM精填: 输入ASR文本+模板, 输出填充后的完整报告"""
    client = _get_llm_client()

    user_msg = f"""## 检查类型
{exam_type}

## 医生口述
{asr_text}

## 填充模板
{template}

请将口述中的测量值填入模板：

1. [选项A;选项B;选项C] → 只保留医生提到的选项
2. mm → 填入实际数值
3. 缺失值保留 ___mm
4. 用 <b class="voice">值</b> 标记AI填充的数值
5. 直接输出填充后的完整报告文本，不要JSON包装"""

    for attempt in range(2):
        try:
            response = client.chat.completions.create(
                model="deepseek-chat",
                messages=[
                    {"role": "system", "content": FILL_SYSTEM_PROMPT},
                    {"role": "user", "content": user_msg},
                ],
                temperature=0.05,
                max_tokens=3000,
            )
            result = response.choices[0].message.content or ""
            # 尝试提取JSON
            if result.strip().startswith("{"):
                obj = json.loads(_extract_json(result))
                return obj.get("filled_text", obj.get("filled", result))
            return result.strip()
        except Exception as e:
            if attempt < 1:
                time.sleep(0.5)
                continue
            _log.warning(f"LLM fill failed: {e}")
            # Fallback: 用正则做最基础的填充
            return basic_regex_fill(asr_text, template)


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


def basic_regex_fill(asr_text: str, template: str) -> str:
    """正则兜底填充: 在没有LLM时的最基础替代"""
    result = template

    # 处理 [选项A;选项B] 格式 - 选择在ASR文本中出现最多的
    def pick_option(m):
        content = m.group(1)
        if ';' in content:
            parts = [p.strip() for p in content.split(';') if p.strip()]
            for p in parts:
                clean_p = re.sub(r'[\[\]\(\)（）]', '', p)
                if clean_p in asr_text:
                    return p
            # 没有匹配的 → 保留最后一个(大概率是默认)
            return parts[-1]
        return m.group(0)

    result = re.sub(r'\[([^\]]+(?:;[^\]]+)+)\]', pick_option, result)

    # 标记未填充的mm
    result = re.sub(
        r'(___?\s*(?:mm|cm|毫米|厘米)?|未测)',
        r'<i class="unfill">\1</i>', result
    )

    # 标记数值
    def mark_voice(m):
        val = m.group(0)
        if '<' in val:
            return val
        return f'<b class="voice">{val}</b>'
    result = re.sub(
        r'\b\d+(?:\.\d+)?\s*(?:mm|cm|毫米|厘米|次/分|克|平方厘米|级)?',
        mark_voice, result
    )

    return result


# ── 4. 端到端 API ──
def anchored_structure(text: str, exam_type: str = "腹部超声",
                        patient_id: str | None = None,
                        skip_llm: bool = False) -> dict:
    """
    模板锚定结构化 — D路径主函数
    0. 极速段落匹配 (44张模板, O(1)哈希, 微秒级)
    1. 精确模板匹配 (top-5候选)
    2. 选最优模板
    3. LLM精填变量 (或正则兜底)
    4. 返回结构化报告
    """
    from template_loader import load_templates, get_template_by_name
    load_templates()

    start_time = time.time()

    # Step 0: 极速段落匹配 (覆盖80%常规报告, 不走LLM)
    try:
        from section_match_engine import match_sections, assemble_report
        exam_cat_map = {
            "腹部超声": "腹部综合", "泌尿前列腺": "腹部综合",
            "甲状腺超声": "甲状腺", "血管超声": "颈动脉",
            "乳腺超声": "乳腺", "妇产超声": "妇科", "心脏超声": "心脏",
        }
        section_cat = exam_cat_map.get(exam_type, None)
        section_matches = match_sections(text, exam_category=section_cat, min_hits=1)

        if section_matches and section_matches[0]["hits"] >= 2:
            # 高信心段落匹配: 直接组装报告, 跳过LLM
            assembled = assemble_report(section_matches, asr_text=text)
            if assembled["study_see_text"]:
                elapsed = time.time() - start_time
                hints = []
                for i, hint in enumerate(assembled.get("study_hint_list", [])[:3]):
                    hints.append({
                        "rank": i + 1,
                        "diagnosis": hint,
                        "icd10": "",
                        "id": f"h{i}",
                        "checked": True,
                    })
                report = {
                    "patient_info": {"name": None, "gender": None, "age": None, "exam_id": None},
                    "exam_info": {"modality": exam_type, "device": None, "exam_date": None},
                    "study_see": assembled["study_see_text"],
                    "study_hint": hints,
                    "recommendation": "",
                    "_template_matched": section_matches[0]["section_id"],
                    "_method": "section_match",
                }
                return {
                    "success": True,
                    "report": report,
                    "report_id": None,
                    "method": "section_match",
                    "warnings": [],
                    "template_used": section_matches[0]["section_id"],
                    "confidence": section_matches[0]["confidence_pct"] / 100,
                    "conflicts": [],
                    "sources": {
                        "A_asr": text[:300],
                        "section_matches": [
                            {"id": m["section_id"], "hits": m["hits"], "text": m["section_text"][:60]}
                            for m in section_matches[:5]
                        ],
                    },
                    "elapsed_ms": round(elapsed * 1000),
                }
    except Exception:
        _log.debug("Section match engine not available, falling through")

    # Step 1: 精确模板匹配
    candidates = match_exact_template(text, exam_type)
    if not candidates:
        # Fallback to old path
        from main import _rule_fallback
        return _rule_fallback(text, exam_type, patient_id)

    best = candidates[0]
    template_name = best["tpl_name"]
    info1 = best.get("info1", "")

    # 如果模板INFO1太短(<20字), 从CSV补全或使用get_template_by_name
    if not info1 or len(info1) < 20:
        tpl = get_template_by_name(template_name)
        if tpl:
            info1 = tpl.get("info1", "")

    # Step 2: 解析模板变量
    parsed = parse_template_variables(info1)
    var_count = parsed["total_variables"]

    # Step 3: LLM精填 (或正则兜底)
    if skip_llm or var_count == 0 or not os.getenv("DEEPSEEK_API_KEY"):
        filled_html = basic_regex_fill(text, info1)
        method = "anchored_regex"
    else:
        filled_html = llm_fill_template(text, info1, exam_type)
        method = "anchored_llm"

    elapsed = time.time() - start_time

    # 提取提示
    study_hint = []
    if best.get("level3"):
        study_hint.append({
            "rank": 1,
            "diagnosis": f"{best['level3']} - {best['tpl_name']}",
            "icd10": "",
            "id": "h0",
            "checked": True,
        })

    report = {
        "patient_info": {"name": None, "gender": None, "age": None, "exam_id": None},
        "exam_info": {"modality": exam_type, "device": None, "exam_date": None},
        "study_see": filled_html,
        "study_hint": study_hint,
        "recommendation": "",
        "_template_matched": template_name,
        "_method": method,
    }

    return {
        "success": True,
        "report": report,
        "report_id": None,
        "method": method,
        "warnings": [],
        "template_used": template_name,
        "confidence": best.get("score", 300) / 400,
        "conflicts": [],
        "sources": {
            "A_asr": text[:300],
            "candidates": [{"name": c["tpl_name"], "score": c["score"]} for c in candidates[:3]],
        },
        "elapsed_ms": round(elapsed * 1000),
    }


# ── 5. 自测 ──
if __name__ == "__main__":
    import sys
    test_text = sys.argv[1] if len(sys.argv) > 1 else "肝脏大小形态正常，包膜光滑，实质回声均匀。胆囊大小约68×28mm，壁光滑，腔内未见异常回声。胰腺形态大小正常。脾脏肋间厚32mm。双肾大小形态正常。"
    exam = sys.argv[2] if len(sys.argv) > 2 else "腹部超声"

    print("=== Template Anchoring Test ===")
    print(f"Input: {test_text[:80]}...")
    print()

    result = anchored_structure(test_text, exam)
    print(f"Method: {result['method']}")
    print(f"Template: {result['template_used']}")
    print(f"Confidence: {result['confidence']:.2f}")
    print(f"Time: {result.get('elapsed_ms', 0)}ms")
    print(f"Candidates: {json.dumps(result['sources'].get('candidates', []), ensure_ascii=False)[:200]}")
    study_see = result['report'].get('study_see', '')
    if study_see:
        # Strip HTML for display
        clean = re.sub(r'<[^>]+>', '', study_see)
        print(f"\nOutput (first 500 chars):")
        print(clean[:500])
