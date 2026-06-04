"""规则引擎 — 加载master_rules.json, 预编译正则, 提供get_rule(), 支持热重载"""

import json, re, os, logging
from pathlib import Path

_log = logging.getLogger(__name__)

RULES_DIR = Path(__file__).parent / "knowledge"
RULES_FILE = RULES_DIR / "master_rules.json"

_rules: dict = {}
_compiled: dict = {}
_loaded = False


def load_rules(force: bool = False) -> dict:
    global _rules, _compiled, _loaded
    if _loaded and not force:
        return _rules

    if not RULES_FILE.exists():
        _log.warning(f"规则文件不存在: {RULES_FILE}")
        _loaded = True
        return _rules

    with open(RULES_FILE, encoding="utf-8") as f:
        _rules = json.load(f)

    # 预编译所有正则表达式
    _compiled = {}
    _precompile(_rules, "")

    _loaded = True
    version = _rules.get("meta", {}).get("version", "?")
    _log.info(f"规则引擎加载完成: version={version}, 预编译{len(_compiled)}个正则")
    return _rules


def _precompile(obj, path_prefix):
    """递归预编译所有pattern字段"""
    if isinstance(obj, dict):
        for k, v in obj.items():
            cur = f"{path_prefix}.{k}" if path_prefix else k
            if k == "pattern" and isinstance(v, str):
                try:
                    _compiled[cur] = re.compile(v)
                except re.error as e:
                    _log.warning(f"正则编译失败 {cur}: {e}")
            else:
                _precompile(v, cur)
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            cur = f"{path_prefix}[{i}]"
            if isinstance(item, dict) and "pattern" in item:
                pat = item["pattern"]
                try:
                    _compiled[f"{cur}.pattern"] = re.compile(pat)
                    item["_compiled"] = _compiled[f"{cur}.pattern"]
                except re.error as e:
                    _log.warning(f"正则编译失败 {cur}: {e}")
            else:
                _precompile(item, cur)


def get_rule(path: str, default=None):
    """点分路径访问规则, 如 get_rule('validation.sex_guard.female_only')"""
    if not _loaded:
        load_rules()

    parts = path.split(".")
    node = _rules
    for p in parts:
        if isinstance(node, dict) and p in node:
            node = node[p]
        else:
            return default
    return node


def get_compiled(path: str, default=None):
    """获取预编译的正则对象, 如 get_compiled('extraction.fetal_measurements[0].pattern')"""
    if not _loaded:
        load_rules()
    return _compiled.get(path, default)


def reload_rules():
    """热重载规则 (文件变更时调用)"""
    global _rules, _compiled, _loaded
    _rules = {}
    _compiled = {}
    _loaded = False
    return load_rules(force=True)


# 自动加载
load_rules()
