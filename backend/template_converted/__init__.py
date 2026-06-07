"""结构化超声模板注册器"""
import re, os, json, csv
from pathlib import Path

_HERE = Path(__file__).resolve().parent

# 模板注册表: {template_name: {html, fields, measurements, options, opt_reset, option_keys}}
_TEMPLATE_REGISTRY: dict = {}
_CSV_INDEX: dict[str, dict] = {}


def register_templates(templates: dict[str, dict], category: str = ""):
    """注册一批模板到注册表"""
    for name, tpl in templates.items():
        tpl.setdefault("measurements", [])
        tpl.setdefault("options", [])
        tpl.setdefault("opt_reset", {})
        tpl.setdefault("option_keys", [])
        tpl.setdefault("fields", {})
        tpl.setdefault("category", category)
        _TEMPLATE_REGISTRY[name] = tpl


# 导入所有自动生成的模板模块
from template_converted.abdomen import *   # 79 templates
from template_converted.gynecology import *  # 52 templates
from template_converted.thyroid import *   # 42 templates
from template_converted.breast import *    # 44 templates
from template_converted.cardiac import *   # 59 templates
from template_converted.other import *     # 83 templates
from template_converted.urology import *   # 50 templates
from template_converted.vascular import *  # 52 templates
from template_converted.obstetrics import * # 3 templates


def _load_csv():
    """加载CSV模板信息用于查找"""
    csv_path = Path(os.environ.get("TEMPLATE_DIR", str(_HERE.parent / "knowledge"))) / "1长沙范本.csv"
    if not csv_path.exists():
        return
    with open(csv_path, encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            name = (row.get("DISCNAME") or "").strip()
            if not name or name in ("0", "NULL"):
                continue
            info1 = (row.get("INFO1") or "").strip()
            info2 = (row.get("INFO2") or "").strip()
            group = (row.get("DISCGROUP") or "").strip()
            module = (row.get("MODULENAME") or "").strip()
            _CSV_INDEX[name] = {
                "category": group or module or "其他",
                "group": group,
                "module": module,
                "info1": info1,
                "info2": info2,
            }


def setup():
    """初始化：加载CSV索引 + 所有注册的模板"""
    _load_csv()


def lookup_template(name: str) -> dict | None:
    """按模板名称查找结构化模板"""
    return _TEMPLATE_REGISTRY.get(name)


def has_template(name: str) -> bool:
    return name in _TEMPLATE_REGISTRY


def template_count() -> int:
    return len(_TEMPLATE_REGISTRY)


def csv_info(name: str) -> dict | None:
    """获取CSV中的模板原始信息"""
    return _CSV_INDEX.get(name)


def all_names() -> list[str]:
    return list(_TEMPLATE_REGISTRY.keys())
