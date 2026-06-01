"""正式超声报告模板加载器 — 从 CSV 导入 4871 条疾病模板"""

import csv
import re
from pathlib import Path
from collections import defaultdict

# 模板目录路径（指向桌面超声结构化报告文件夹）
TEMPLATE_DIR = Path(r"C:\Users\Administrator\Desktop\超声结构化报告")

# 内存缓存
_template_index: dict[str, list[dict]] = defaultdict(list)
_templates_loaded = False
_keyword_index: dict[str, str] = {}  # 关键词 → DISCNAME 精确匹配


def load_templates() -> dict[str, list[dict]]:
    """加载正式模板表到内存（懒加载，只加载一次）"""
    global _templates_loaded, _template_index, _keyword_index

    if _templates_loaded:
        return dict(_template_index)

    csv_path = TEMPLATE_DIR / "模板表.csv"
    if not csv_path.exists():
        _templates_loaded = True
        return {}

    with open(csv_path, encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            name = (row.get("DISCNAME") or "").strip()
            if not name or name in ("0", "NULL"):
                continue
            visc = (row.get("VISCNAME") or "").strip()
            info1 = (row.get("INFO1") or "").strip()
            info2 = (row.get("INFO2") or "").strip()
            modname = (row.get("MODULENAME") or "").strip()
            group = (row.get("DISCGROUP") or "").strip()

            entry = {
                "name": name,
                "visc": visc,
                "info1": info1,  # 所见模板
                "info2": info2,  # 提示模板
                "module": modname,
                "group": group,
            }

            # 按模块名分组
            module_key = modname or "general"
            _template_index[module_key].append(entry)

            # 建立关键词索引
            _keyword_index[name] = name
            # 也索引简写（去掉括号内容）
            clean = re.sub(r"[\[\(（].*?[\]\)）]", "", name).strip()
            if clean and clean != name:
                _keyword_index[clean] = name

    _templates_loaded = True
    print(f"[模板加载] 共加载 {sum(len(v) for v in _template_index.values())} 条模板，"
          f"{len(_template_index)} 个模块")
    return dict(_template_index)


def match_template(text: str, exam_type: str = "") -> dict | None:
    """
    根据医生口述文本匹配最合适的正式模板。
    返回匹配到的模板条目，或 None。
    """
    templates = load_templates()
    if not templates:
        return None

    # 策略1：关键词精确匹配 DISCNAME
    for keyword in sorted(_keyword_index.keys(), key=len, reverse=True):
        if keyword in text:
            name = _keyword_index[keyword]
            # 在所有模块中查找
            for entries in templates.values():
                for e in entries:
                    if e["name"] == name:
                        return e

    # 策略2：无匹配时返回 None，LLM 自由发挥
    return None


def match_templates_multi(text: str, exam_type: str = "", max_results: int = 3) -> list[dict]:
    """返回匹配到的多个模板（按匹配质量排序）"""
    templates = load_templates()
    if not templates:
        return []

    results = []
    matched_names = set()

    for keyword in sorted(_keyword_index.keys(), key=len, reverse=True):
        if keyword in text and len(results) < max_results:
            name = _keyword_index[keyword]
            if name in matched_names:
                continue
            matched_names.add(name)
            for entries in templates.values():
                for e in entries:
                    if e["name"] == name:
                        results.append(e)
                        break

    return results


def extract_options(text: str) -> list[list[str]]:
    """从模板文本中提取 [选项1;选项2;选项3] 语法"""
    return re.findall(r"\[([^\]]*?)\]", text)


def format_template_for_prompt(entry: dict) -> str:
    """将一条正式模板格式化为 LLM 参考文本"""
    parts = []
    if entry.get("info1"):
        # 清理选项语法，转为更清爽的格式
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
    """返回所有疾病名称列表"""
    load_templates()
    return sorted(set(_keyword_index.values()))
