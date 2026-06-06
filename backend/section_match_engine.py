#!/usr/bin/env python3
"""
超声报告混合匹配引擎 v3
三层级联:
  Layer 1: 核心模板极速匹配 (33张, ~80%覆盖, <1ms)
  Layer 2: 扩展热词库匹配 (638张, ~91%覆盖, ~5ms)
  Layer 3: LLM兜底 (剩余~9%)

策略:
  L1: 33张核心模板 + 变量展开 → 关键词反向索引哈希
  L2: 对L1未命中的, 遍历扩展热词库(638-33=605张) → 仍用关键词哈希, 但阈值降低
  L3: L1+L2都未命中 → template_anchor全文匹配 → LLM
"""

import json, re, time, logging
from pathlib import Path
from collections import defaultdict, Counter

_log = logging.getLogger(__name__)

HERE = Path(__file__).parent
TPL_FILE = HERE / "knowledge" / "section_templates_merged.json"
RULES_FILE = HERE / "knowledge" / "matching_rules_merged.json"
# 扩展索引 (638张覆盖~91%)
EXT_INDEX_FILE = HERE / "knowledge" / "extended_hotword_index.json"

# 缓存
_core_rules = None     # {keyword: [(tid, category), ...]}
_core_templates = None
_ext_rules = None
_ext_templates = None


def _load_core():
    global _core_rules, _core_templates
    if _core_rules is not None:
        return
    _core_rules = defaultdict(list)
    _core_templates = {}
    with open(RULES_FILE, encoding='utf-8') as f:
        rules = json.load(f)
    with open(TPL_FILE, encoding='utf-8') as f:
        _core_templates = json.load(f)
    for tid, rule in rules.items():
        if tid not in _core_templates:
            continue
        cat = rule.get('category', '')
        for kw in rule.get('keywords', []):
            k = kw.lower().strip()
            if k and len(k) >= 2:
                _core_rules[k].append((tid, cat))


def _norm(text):
    t = re.sub(r'\s+', '', text)
    t = t.replace(',', '，').replace(';', '；').replace(':', '：').replace('：', '：')
    return t


def match_sections(asr_text, exam_category=None, min_hits=1):
    """核心模板匹配 (原接口)"""
    t0 = time.time()
    _load_core()

    normalized = _norm(asr_text)
    hit_map = defaultdict(lambda: {"hits": 0, "matched_kw": []})

    for keyword, entries in _core_rules.items():
        if keyword in normalized:
            for tid, cat in entries:
                if exam_category and cat != exam_category:
                    continue
                hit_map[tid]["hits"] += 1
                hit_map[tid]["matched_kw"].append(keyword)
                hit_map[tid]["category"] = cat

    results = []
    for tid, hit_info in hit_map.items():
        hits = hit_info["hits"]
        if hits < min_hits:
            continue
        tpl = _core_templates.get(tid, {})
        tpl_text = tpl.get("text", "")

        # 方向检测
        if "E＞A" in tpl_text or "E>A" in tpl_text:
            if any(x in normalized for x in ["E＜A", "E<A", "E小于A"]) and \
               not any(x in normalized for x in ["E＞A", "E>A", "E大于A"]):
                continue
        if "E＜A" in tpl_text or "E<A" in tpl_text:
            if any(x in normalized for x in ["E＞A", "E>A", "E大于A"]) and \
               not any(x in normalized for x in ["E＜A", "E<A", "E小于A"]):
                continue

        results.append({
            "section_id": tid, "section_text": tpl_text,
            "category": tpl.get("category", ""), "hits": hits,
            "keywords_matched": hit_info["matched_kw"],
            "confidence_pct": min(100, hits * 40),
            "layer": 1,
        })

    results.sort(key=lambda x: -x["hits"])
    return results


def expand_variable_template(template_text, asr_text):
    """展开 [A;B] 变量, 忽略标点差异 + 数字归一化"""
    # 归一化 ASR 中的数字, 与模板的 #x# 占位符对齐
    nasr = re.sub(r'\d+\.?\d*\s*[xX×]\s*\d+\.?\d*', '#x#', asr_text)
    nasr = re.sub(r'\d+\.?\d+\s*mm', '#mm', nasr)
    nasr = re.sub(r'\d+\.?\d+\s*%', '#%', nasr)
    nasr = re.sub(r'\d+\.?\d+', '#', nasr)
    clean_asr = re.sub(r'[，。；;：:\s、]', '', nasr)

    def _pick(m):
        content = m.group(1)
        parts = content.split(';')
        best = ''; best_len = 0
        for p in parts:
            clean_p = re.sub(r'[，。\s、]', '', p)
            if clean_p and clean_p in clean_asr and len(clean_p) > best_len:
                best = p; best_len = len(clean_p)
        if best:
            return best
        # No match in ASR: prefer empty (delete optional), else pick first non-empty
        if '' in parts:
            return ''
        non_empty = [p for p in parts if p]
        return non_empty[0] if non_empty else ''
    return re.sub(r'\[([^\]]*)\]', _pick, template_text)


def assemble_report(sections, asr_text=""):
    """组装报告"""
    if not sections:
        return {"study_see_text": "", "study_hint_list": [], "categories_covered": []}

    ORGAN_KW = {
        "胆囊": ["胆囊", "胆总管", "胆内", "息肉"],
        "肝脏": ["肝脏", "肝内", "肝表面", "门静脉", "门脉", "肝管"],
        "双肾": ["双肾", "右肾", "左肾", "肾盂", "肾实质", "集合系"],
        "脾": ["脾厚", "脾脏", "脾门"],
        "胰": ["胰头", "胰体", "胰管", "胰腺"],
        "膀胱": ["膀胱"],
        "前列腺": ["前列腺"],
        "心脏": ["心脏", "二尖瓣", "三尖瓣", "心室", "心房", "房室", "室间隔", "心包"],
        "甲状腺": ["甲状腺", "颈部淋巴结", "结节内", "TI-RADS", "峡部"],
        "颈动脉": ["颈动脉", "颈总", "颈内", "斑块"],
        "附件": ["附件", "子宫", "卵巢", "盆腔"],
        "输尿管": ["输尿管"],
    }

    organ_best = {}
    for sec in sections:
        organ = "其他"
        for o, kws in ORGAN_KW.items():
            for kw in kws:
                if kw in sec["section_text"]:
                    organ = o; break
            if organ != "其他": break
        if organ not in organ_best or sec["hits"] > organ_best[organ]["hits"]:
            organ_best[organ] = sec

    deduped_sections = sorted(organ_best.values(), key=lambda x: -x["hits"])
    all_paragraphs = [sec["section_text"] for sec in deduped_sections]
    categories_covered = list(set(sec["category"] for sec in deduped_sections))

    # 去重+子集
    seen = set(); deduped = []
    for p in all_paragraphs:
        clean = re.sub(r'[^一-鿿]', '', p)
        if clean not in seen:
            is_subset = False
            clean_p = re.sub(r'[\[;\]\s]', '', p)
            for existing in deduped:
                clean_ex = re.sub(r'[\[;\]\s]', '', existing)
                if clean_p in clean_ex:
                    is_subset = True; break
                if clean_ex in clean_p:
                    deduped.remove(existing)
                    seen = {re.sub(r'[^一-鿿]', '', d) for d in deduped}
                    break
            if not is_subset:
                seen.add(clean); deduped.append(p)

    if asr_text:
        deduped = [expand_variable_template(p, asr_text) for p in deduped]

    hints = []
    for sec in sections[:5]:
        tpl = _core_templates.get(sec["section_id"], {})
        for hint in tpl.get("top_hints", [])[:2]:
            if hint not in hints: hints.append(hint)

    return {"study_see_text": "\n".join(deduped),
            "study_hint_list": hints[:3],
            "categories_covered": categories_covered}
