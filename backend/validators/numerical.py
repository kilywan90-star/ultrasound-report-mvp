"""
超声语音报告系统 — 数值范围校验器
服务端硬校验提取的数值是否在生理合理范围内
"""

import re
import logging
from rule_engine import get_rule

_log = logging.getLogger(__name__)

# 单位转换因子 (转为标准单位)
_UNIT_TO_STANDARD = {
    "mm": {"mm": 1.0, "cm": 10.0, "毫米": 1.0, "厘米": 10.0},
    "cm": {"mm": 0.1, "cm": 1.0, "毫米": 0.1, "厘米": 1.0},
    "次/分": {"次/分": 1.0},
    "克": {"克": 1.0, "公斤": 1000.0},
    "平方厘米": {"平方厘米": 1.0},
}


def _strip_html(html: str) -> str:
    """移除HTML标签，返回纯文本"""
    return re.sub(r'<[^>]+>', '', html or "")


def _extract_number_unit_pairs(text: str) -> list[dict]:
    """从文本中提取数值+单位对，并记录位置"""
    pattern = r'(\d+(?:\.\d+)?)\s*(mm|cm|毫米|厘米|次/分|克|平方厘米)'
    results = []
    for m in re.finditer(pattern, text):
        results.append({
            "value": float(m.group(1)),
            "unit": m.group(2),
            "start": m.start(),
            "end": m.end(),
            "match": m.group(0),
        })
    return results


def _find_field_for_position(text: str, pos: int, field_hints: dict) -> str | None:
    """根据数值位置前的上下文关键词，判断属于哪个字段"""
    window_start = max(0, pos - 30)
    window = text[window_start:pos]

    best_field = None
    best_score = 0

    for field_id, info in field_hints.items():
        keywords = info.get("keywords", [])
        for kw in keywords:
            if kw in window:
                kw_pos = window.rfind(kw)
                distance = len(window) - kw_pos
                score = 100 - distance
                if score > best_score:
                    best_score = score
                    best_field = field_id

    return best_field


def _normalize_value(value: float, from_unit: str, to_unit: str) -> float:
    """将数值从from_unit转换为to_unit"""
    if from_unit == to_unit:
        return value
    conversions = _UNIT_TO_STANDARD.get(to_unit, {})
    factor = conversions.get(from_unit, 1.0)
    return value * factor


def validate_numerical_ranges(html_text: str) -> list[dict]:
    """
    服务端数值范围校验

    从HTML中提取数值，根据上下文关键词映射到字段，
    然后检查是否在field_asr_hints定义的合理范围内。

    Returns:
        list[dict]: 每个元素包含:
            - field: 字段ID
            - value: 原始数值
            - unit: 原始单位
            - normalized_value: 转换后的数值
            - range: [min, max]
            - severity: "warning" 或 "error"
            - message: 人可读的警告信息
    """
    field_hints = get_rule("extraction.field_asr_hints", {})
    if not field_hints:
        return []

    text = _strip_html(html_text)
    pairs = _extract_number_unit_pairs(text)

    warnings = []
    for pair in pairs:
        field_id = _find_field_for_position(text, pair["start"], field_hints)
        if not field_id:
            continue

        info = field_hints[field_id]
        expected_unit = info.get("unit", "")
        range_val = info.get("range", [])

        if len(range_val) != 2:
            continue

        min_val, max_val = range_val

        # 单位转换
        normalized = _normalize_value(pair["value"], pair["unit"], expected_unit)

        # 范围检查
        if normalized < min_val or normalized > max_val:
            if normalized < min_val:
                deviation = (min_val - normalized) / max(min_val, 0.01)
            else:
                deviation = (normalized - max_val) / max(max_val, 0.01)

            severity = "error" if deviation >= 0.5 else "warning"

            msg = (f"{field_id}={pair['value']}{pair['unit']}"
                   f"(转换后{normalized:.1f}{expected_unit})"
                   f"超出合理范围[{min_val}-{max_val}{expected_unit}]")

            warnings.append({
                "field": field_id,
                "value": pair["value"],
                "unit": pair["unit"],
                "normalized_value": normalized,
                "expected_unit": expected_unit,
                "range": range_val,
                "severity": severity,
                "message": msg,
            })

    if warnings:
        _log.info(f"数值范围校验发现 {len(warnings)} 个问题")

    return warnings
