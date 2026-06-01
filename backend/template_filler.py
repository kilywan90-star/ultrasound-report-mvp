"""纯正则模板填充"""

import re, csv, os
from pathlib import Path
from pathlib import Path
from collections import defaultdict

TEMPLATE_CSV = Path(os.environ.get("TEMPLATE_DIR", r"C:\Users\Administrator\Desktop\超声结构化报告")) / "模板表.csv"
_templates: list[dict] = []
_fulltext: dict[str, list[int]] = defaultdict(list)
_categories: dict[str, list[int]] = defaultdict(list)
_names: dict[str, int] = {}  # cleaned_name → idx
_loaded = False

MANUAL = {
    "妊娠": ["异位妊娠","中孕合并子宫肌瘤"],
    "四维": ["中孕合并子宫肌瘤"], "早孕": ["异位妊娠"],
    "单活胎": ["中孕合并子宫肌瘤"], "胎": ["中孕合并子宫肌瘤","异位妊娠"],
    "结石": ["胆囊结石","肾结石"], "胆结石": ["胆囊结石"],
    "肝囊肿": ["*多发性肝囊肿"], "肾囊肿": ["*多发性肾囊肿","肾盂源性囊肿"],
    "卵巢囊肿": ["卵巢囊肿"], "子宫肌瘤": ["子宫粘膜下肌瘤","子宫内膜炎下肌瘤"],
    "脂肪肝": ["脂肪肝"], "肝硬化": ["肝硬化"],
    "血管瘤": ["肝血管瘤"], "息肉": ["胆囊息肉"],
    "积水": ["肾积水"], "腹水": ["腹水"], "脾大": ["脾大"],
    "增生": ["前列腺增生"], "钙化": ["前列腺钙化"],
}

SITE_DISEASE = {
    "胆": {"囊肿": "肝囊肿","结石": "胆囊结石","息肉": "胆囊息肉"},
    "肝": {"囊肿": "肝囊肿","结石": "肝内胆管结石","血管瘤": "肝血管瘤","脂肪": "脂肪肝"},
    "肾": {"囊肿": "肾囊肿","结石": "肾结石","积水": "肾积水"},
    "子宫": {"肌瘤": "子宫肌瘤","腺肌": "子宫腺肌症","息肉": "子宫内膜息肉"},
    "卵巢": {"囊肿": "卵巢囊肿","畸胎瘤": "卵巢畸胎瘤"},
    "膀胱": {"结石": "膀胱结石"}, "前列腺": {"增生": "前列腺增生"},
    "胰": {"炎": "急性胰腺炎"}, "脾": {"大": "脾大"},
    "甲状": {"结节": "甲状腺结节"}, "乳腺": {"结节": "乳腺结节"},
    "颈动": {"斑块": "颈动脉斑块","狭窄": "颈动脉狭窄","血栓": "深静脉血栓"},
}


def _load():
    global _loaded, _templates, _fulltext, _categories, _names
    if _loaded: return
    if not TEMPLATE_CSV.exists(): _loaded = True; return

    organs = ["肝脏","胆囊","胆总管","胰腺","脾脏","肾脏","左肾","右肾","双肾",
              "膀胱","前列腺","子宫","卵巢","附件","盆腔","胎儿","甲状腺",
              "乳腺","颈动脉","腹主动脉","心脏","二尖瓣","主动脉瓣","心包",
              "妊娠","早孕","中孕","晚孕","胎","孕","产"]

    with open(TEMPLATE_CSV, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            name = (row.get("DISCNAME") or "").strip()
            if not name or name in ("0","NULL"): continue
            info1 = (row.get("INFO1") or "").strip()
            info2 = (row.get("INFO2") or "").strip()
            has_mm = "mm" in info1
            has_org = any(o in info1 for o in organs)
            clean = re.sub(r"[\[\]\(\);\"\s+\-RTFrtf\\\{}]+","",info1)
            if not ((has_mm or has_org) and len(clean) > 30): continue

            idx = len(_templates)
            _templates.append({"name":name,"info1":info1,"info2":info2})
            # cleaned name
            cn = re.sub(r"[\[\(（].*?[\]\)）\*]","",name).strip()
            if cn and cn not in _names: _names[cn] = idx

            # categories
            if any(o in info1 for o in ["子宫","卵巢","附件","胎儿","妊娠","孕"]): _categories["obgyn"].append(idx)
            if any(o in info1 for o in ["肝脏","胆囊","胰腺","脾脏","肾脏","膀胱","前列腺"]): _categories["abdm"].append(idx)
            if any(o in info1 for o in ["心脏","二尖瓣","主动脉瓣","心包","心室","心房","瓣"]): _categories["card"].append(idx)
            if any(o in info1 for o in ["甲状腺","乳腺","淋巴结","睾丸","腮腺","颈动脉"]): _categories["thyr"].append(idx)
            if any(o in info1 for o in ["动脉","静脉","血栓","斑块","流速","IMT"]): _categories["vasc"].append(idx)

    # Fulltext index on all template text
    for i, t in enumerate(_templates):
        all_text = t["name"]+" "+t["info1"]+" "+t["info2"]
        for w in set(re.findall(r"[一-鿿]{2,6}", all_text)):
            _fulltext[w].append(i)

    _loaded = True


def _search(text: str) -> list[int]:
    """搜索函数：返回模板索引列表（按相关性排序）"""
    _load()
    score: dict[int, float] = {}

    # 1. DISCNAME 完全匹配 (score = 100+)
    for cn, idx in _names.items():
        if len(cn) >= 3 and cn in text:
            score[idx] = max(score.get(idx, 0), 100 + len(cn) * 2)

    # 2. SITE + DISEASE 交叉匹配 (找同时包含部位词和病变词的模板)
    site_words = ["胆","肝","肾","子宫","卵巢","膀胱","前列腺","胰","脾","甲状","乳腺","颈动","腹主"]
    disease_words = ["结石","囊肿","囊","肌瘤","息肉","增生","钙化","血管瘤","脂肪肝","硬化","积水","腹水","畸胎瘤","狭窄","斑块","血栓","结节","积液","肿","腺肌","炎","大"]

    doc_sites = [s for s in site_words if s in text]
    doc_dis = [d for d in disease_words if d in text]
    for s in doc_sites:
        for d in doc_dis:
            for idx, t in enumerate(_templates):
                # 在 DISCNAME 和 INFO1 中同时出现 → 高置信度
                in_name = (s in t["name"] and d in t["name"])
                in_info = (s in t["info1"] and d in t["info1"])
                in_full_disease = any(fd in t["name"] for fd in ["囊肿","结石","肌瘤","息肉","增生","钙化","血管瘤","脂肪肝","硬化","积水","腹水","畸胎瘤","狭窄","斑块","血栓","结节","积液"])
                if in_name and in_full_disease:
                    score[idx] = max(score.get(idx, 0), 100)  # 全疾病词匹配最高分
                elif in_name:
                    score[idx] = max(score.get(idx, 0), 95)
                elif in_info:
                    score[idx] = max(score.get(idx, 0), 87)

    # 3. MANUAL 映射 (score = 90)
    for kw, names in MANUAL.items():
        if kw not in text: continue
        for dn in names:
            for idx, t in enumerate(_templates):
                if dn in t["name"]:
                    score[idx] = max(score.get(idx, 0), 90)

    # 4. 全文索引补漏 (score < 50)
    if not score:
        for w in set(re.findall(r"[一-鿿]{2,4}", text)):
            for idx in _fulltext.get(w, []):
                score[idx] = score.get(idx, 0) + 1

    ranked = sorted(score.items(), key=lambda x: -x[1])
    high = [i for i, s in ranked if s >= 50]
    if high: return high[:3]
    return [i for i, s in ranked[:3] if s >= 5]


def _extract_numbers(text: str) -> list[str]:
    nums = []
    nums.extend(re.findall(r"\d+(?:\.\d+)?\s*[×xX\*乘]\s*\d+(?:\.\d+)?\s*(?:mm|毫米|cm|厘米)?", text))
    nums.extend(re.findall(r"\d+(?:\.\d+)?\s*(?:mm|毫米|cm|厘米)", text))
    nums.extend(re.findall(r"\d+(?:\.\d+)?\s*毫?米?", text))
    seen, result = set(), []
    for n in nums:
        n = n.strip()
        if n in seen: continue
        seen.add(n)
        if not re.search(r"(mm|毫米|cm|厘米)", n): n += "mm"
        result.append(n)
    return result


def _extract_options(text: str, template: str) -> dict[str, str]:
    choices = {}
    for group in re.findall(r"\[([^\]]*?)\]", template):
        opts = [o.strip().strip('"').strip("'") for o in group.split(";")]
        if len(opts) < 2: continue
        for opt in opts:
            if opt and opt in text: choices[group] = opt; break
        else: choices[group] = opts[0]
    return choices


def _fill(tmpl: str, nums: list[str], opts: dict[str, str]) -> str:
    t = tmpl; ni = [0]
    def r(_):
        if ni[0] < len(nums): v = nums[ni[0]]; ni[0] += 1; return f'<b class="voice">{v}</b>'
        ni[0] += 1; return '<b class="unfill">___mm</b>'
    t = re.sub(r"mm\s*[×Xx\*]\s*mm(\s*[×Xx\*]\s*mm)?", r, t)
    t = re.sub(r"(?<![×Xx\*\s])(?<!\d)mm(?![×Xx\*])", r, t)
    for g, p in opts.items():
        t = t.replace("["+g+"]", p)
    t = re.sub(r"\[([^\]]+)\]", lambda m: m.group(1).split(";")[0].strip().strip('"'), t)
    t = t.replace("+", "\n")
    t = re.sub(r"\n{3,}", "\n\n", t)
    t = re.sub(r"[ ]+", " ", t)
    t = re.sub(r"\\[a-z]+\d*", "", t)
    t = re.sub(r"[\{\}]", "", t)
    return '<div class="rpt-html">'+t.strip()+'</div>'


def _hints(info2: str, opts: dict[str, str], disease_name: str) -> list[dict]:
    t = info2
    for g, p in opts.items(): t = t.replace("["+g+"]", p)
    t = re.sub(r"\[([^\]]+)\]", lambda m: m.group(1).split(";")[0].strip().strip('"'), t)
    t = t.replace("+", "\n").strip()
    hints = []
    for line in t.split("\n"):
        line = line.strip()
        if line and len(line) > 1: hints.append({"rank": len(hints)+1, "diagnosis": line, "icd10": ""})
    if not hints: hints.append({"rank": 1, "diagnosis": disease_name, "icd10": ""})
    return hints


def _cat_fallback(raw_text: str, exam_type: str) -> list[int]:
    """类别回退：按exam_type取模板"""
    cat = ""
    exam = exam_type + raw_text[:50]
    if any(k in exam for k in ("妇产","孕","子宫","卵巢","胎儿","妇科","产科")): cat = "obgyn"
    elif any(k in exam for k in ("心脏","心超","心彩")): cat = "card"
    elif any(k in exam for k in ("甲状腺","乳腺","小器官")): cat = "thyr"
    elif any(k in exam for k in ("血管","颈动脉","动脉","静脉")): cat = "vasc"
    else: cat = "abdm"
    return _categories.get(cat, [])[:5]


def match_and_fill(raw_text: str, exam_type: str = "") -> dict | None:
    _load(); idxs = _search(raw_text)
    if not idxs: idxs = _cat_fallback(raw_text, exam_type)
    if not idxs: return None

    tpl = _templates[idxs[0]]
    nums = _extract_numbers(raw_text)
    opts = _extract_options(raw_text, tpl["info1"])
    see = _fill(tpl["info1"], nums, opts)
    hint = _hints(tpl["info2"], opts, tpl["name"])

    return {
        "patient_info": {"name": None, "gender": None, "age": None, "exam_id": None},
        "exam_info": {"modality": exam_type or "超声", "device": None, "exam_date": None},
        "study_see": see, "study_hint": hint, "recommendation": "",
        "_template_matched": tpl["name"], "_method": "regex_fill",
    }
