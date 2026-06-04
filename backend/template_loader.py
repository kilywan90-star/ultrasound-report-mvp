"""正式超声报告模板加载器 — v3: 加载长沙医院模板123.csv"""

import csv, os, re
from pathlib import Path
from collections import defaultdict, OrderedDict

TEMPLATE_DIR = Path(os.environ.get("TEMPLATE_DIR", r"C:\Users\Administrator\Desktop\超声结构化报告"))
TEMPLATE_CSV = TEMPLATE_DIR / "长沙医院模板123.csv"

_template_index: OrderedDict[str, dict] = OrderedDict()
_templates_loaded = False
_keyword_index: dict[str, str] = {}
_category_index: dict[str, list[str]] = defaultdict(list)
_module_index: dict[str, list[str]] = defaultdict(list)


def load_templates() -> OrderedDict[str, dict]:
    """加载长沙医院模板CSV到内存（懒加载，只加载一次）"""
    global _templates_loaded, _template_index, _keyword_index, _category_index, _module_index

    if _templates_loaded:
        return _template_index

    if not TEMPLATE_CSV.exists():
        print(f"[模板加载] WARNING: 模板文件不存在: {TEMPLATE_CSV}")
        _templates_loaded = True
        return _template_index

    with open(TEMPLATE_CSV, encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            name = (row.get("DISCNAME") or "").strip()
            if not name or name in ("0", "NULL"):
                continue

            info1 = (row.get("INFO1") or "").strip()
            info2 = (row.get("INFO2") or "").strip()
            module = (row.get("MODULENAME") or "其他").strip()
            group = (row.get("DISCGROUP") or "").strip()
            visc = (row.get("VISCNAME") or "").strip()

            entry = {
                "name": name,
                "info1": info1,
                "info2": info2,
                "module": module,
                "group": group,
                "visc": visc,
            }

            _template_index[name] = entry

            # 关键词索引
            clean = re.sub(r"[\[\(（].*?[\]\)）\*]", "", name).strip()
            if clean:
                _keyword_index[clean] = name
            _keyword_index[name] = name

            # 类别索引
            if group:
                _category_index[group].append(name)
            if module:
                _module_index[module].append(name)

    _templates_loaded = True
    print(f"[模板加载] 长沙医院模板: {len(_template_index)}条, "
          f"{len(_module_index)}个模块, {len(_category_index)}个分组")
    return _template_index


def get_template_by_name(name: str) -> dict | None:
    """精确获取一条模板的完整信息"""
    load_templates()
    return _template_index.get(name)


def search_candidates(text: str, exam_type: str = "", limit: int = 10) -> list[dict]:
    """
    从4871条模板中搜索候选模板列表
    策略: 关键词匹配 DISCNAME + 模块名过滤
    """
    load_templates()
    if not _template_index:
        return []

    scored: dict[str, int] = {}

    # 策略1: DISCNAME关键词精确匹配
    for keyword in sorted(_keyword_index.keys(), key=len, reverse=True):
        if keyword in text and len(keyword) >= 2:
            name = _keyword_index[keyword]
            scored[name] = max(scored.get(name, 0), 100 + len(keyword) * 5)

    # 策略2: 器官词匹配INFO1 (从规则引擎加载)
    from rule_engine import get_rule as _gr
    organ_words = _gr("templates.organ_words", ["肝脏","胆囊","胰腺","脾脏","肾脏","子宫","卵巢"])
    for name, entry in _template_index.items():
        info1 = entry.get("info1", "")
        for organ in organ_words:
            if organ in text and organ in info1:
                scored[name] = scored.get(name, 0) + 20
                break

    # 策略3: 疾病词匹配
    disease_words = _gr("templates.disease_words", ["结石","囊肿","肌瘤","息肉","增生","钙化"])
    for name, entry in _template_index.items():
        info1 = entry.get("info1", "") + entry.get("info2", "")
        for disease in disease_words:
            if disease in text and disease in info1:
                scored[name] = scored.get(name, 0) + 15
                break

    # 策略4: 检查类型模糊匹配模块名 (从规则引擎加载)
    module_map = _gr("templates.module_map", {"腹部": ["UIS"]})
    matched_modules = set()
    for kw, mods in module_map.items():
        if kw in exam_type or kw in text[:80]:
            matched_modules.update(mods)

    for name in list(_template_index.keys()):
        entry = _template_index[name]
        mod = entry.get("module", "")
        # 模块匹配加分 (有明确模块名的模板优先)
        if mod and mod in matched_modules:
            scored[name] = scored.get(name, 0) + 60  # 大幅加分，强过滤
        elif not mod or not mod.strip():
            # 无模块名模板降权 (避免跨类别误匹配)
            scored[name] = scored.get(name, 0) - 20

    # 策略5: 无模块名的模板只在有器官词命中时才保留
    for name in list(scored.keys()):
        if scored[name] <= 0:
            del scored[name]
            continue
        entry = _template_index.get(name, {})
        mod = entry.get("module", "")
        if not mod or not mod.strip():
            # 无模块名模板必须同时命中器官词+疾病词才保留
            has_organ = any(o in (entry.get("info1","") + entry.get("name","")) for o in organ_words)
            has_disease = any(d in (entry.get("info1","") + entry.get("name","") + entry.get("info2","")) for d in disease_words)
            if not (has_organ and has_disease):
                scored[name] = scored.get(name, 0) - 30
                if scored[name] <= 0:
                    del scored[name]

    # 排序取top-N
    ranked = sorted(scored.items(), key=lambda x: -x[1])
    results = []
    for name, score in ranked[:limit * 2]:
        entry = _template_index[name]
        results.append({
            "name": name,
            "module": entry.get("module", ""),
            "group": entry.get("group", ""),
            "info1_preview": entry.get("info1", "")[:300],
            "score": score,
        })

    # 去重按name，截断limit
    seen = set()
    uniq = []
    for r in results:
        if r["name"] not in seen:
            seen.add(r["name"])
            uniq.append(r)
        if len(uniq) >= limit:
            break

    return uniq


def all_module_names() -> list[str]:
    load_templates()
    return sorted(_module_index.keys())


def match_template(text: str, exam_type: str = "") -> dict | None:
    """根据文本匹配最合适的正式模板（保留旧接口兼容）"""
    candidates = search_candidates(text, exam_type, limit=1)
    if candidates:
        return get_template_by_name(candidates[0]["name"])
    return None


def match_templates_multi(text: str, exam_type: str = "", max_results: int = 3) -> list[dict]:
    """返回匹配到的多个模板"""
    candidates = search_candidates(text, exam_type, limit=max_results)
    return [get_template_by_name(c["name"]) for c in candidates if get_template_by_name(c["name"])]


def extract_options(text: str) -> list[list[str]]:
    return re.findall(r"\[([^\]]*?)\]", text)


def format_template_for_prompt(entry: dict) -> str:
    """将一条正式模板格式化为 LLM 参考文本"""
    parts = []
    if entry.get("info1"):
        info1_clean = re.sub(r"\[([^\]]+?)\]", r"[\1]", entry["info1"])
        info1_clean = info1_clean.replace("+", "\n")
        info1_clean = re.sub(r"\s{2,}", " ", info1_clean)
        info1_clean = info1_clean.replace("mm × mm × mm", "___mm × ___mm × ___mm")
        info1_clean = info1_clean.replace("mm X mm X mm", "___mm × ___mm × ___mm")
        info1_clean = re.sub(r"(?<!\d)mm(?![×Xx])", "___mm", info1_clean)
        parts.append(f"【所见格式参考】\n{info1_clean.strip()}")

    if entry.get("info2"):
        info2_clean = entry["info2"].replace("+", "\n")
        parts.append(f"【提示格式参考】\n{info2_clean.strip()}")

    return "\n\n".join(parts)


def all_disease_names() -> list[str]:
    load_templates()
    return sorted(set(_keyword_index.values()))


# 自动加载
load_templates()
