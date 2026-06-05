"""ASR 质量估算器 — 基于4信号加权评分的动态路由决策

信号维度:
  1. 纠错修改率 (correction_rate) — 权重 0.35
  2. 医学术语匹配度 (terminology) — 权重 0.25
  3. 数值模式合理性 (number_validity) — 权重 0.25
  4. 文本结构完整性 (structure) — 权重 0.15

路由决策:
  confidence >= threshold → "fast" (单次轻量LLM)
  confidence < threshold  → "full" (完整ABCDEF流水线)
"""

import re
import logging

_log = logging.getLogger(__name__)

# 默认配置 (可被 master_rules.json 覆盖)
_DEFAULT_CONFIG = {
    "enabled": True,
    "threshold": 0.90,
    "weights": {
        "correction_rate": 0.35,
        "terminology": 0.25,
        "number_validity": 0.25,
        "structure": 0.15,
    },
}


def _load_config() -> dict:
    """从规则引擎加载动态路由配置，失败则用默认值"""
    try:
        from rule_engine import get_rule
        cfg = get_rule("pipeline.dynamic_routing", None)
        if cfg and isinstance(cfg, dict):
            return {**_DEFAULT_CONFIG, **cfg}
    except Exception:
        pass
    return _DEFAULT_CONFIG


# ── 信号 1: 纠错修改率 ──

def _score_correction_rate(correction_stats: dict | None) -> float:
    """基于纠错统计的修改率评分

    rate = edits / len(corrected_text)
    rate=0 → 1.0 (零修改，完美)
    rate<0.01 → 0.95
    rate<0.03 → 0.85
    rate<0.06 → 0.70
    rate>=0.06 → 0.50
    """
    if not correction_stats:
        return -1.0  # 标记为不可用

    rate = correction_stats.get("rate", 0.0)
    if rate == 0:
        return 1.0
    if rate < 0.01:
        return 0.95
    if rate < 0.03:
        return 0.85
    if rate < 0.06:
        return 0.70
    return 0.50


# ── 信号 2: 医学术语匹配度 ──

# 标准脏器/病变术语 (从 CONFUSION_DICT 的 keys 提取)
_CORRECT_TERMS: set = set()
_ERROR_TERMS: list = []

def _init_terms():
    """延迟初始化术语表"""
    global _CORRECT_TERMS, _ERROR_TERMS
    if _CORRECT_TERMS:
        return
    try:
        from asr_correction import CONFUSION_DICT
        _CORRECT_TERMS.update(CONFUSION_DICT.keys())
        for wrongs in CONFUSION_DICT.values():
            _ERROR_TERMS.extend(wrongs)
    except ImportError:
        pass

def _score_terminology(text: str) -> float:
    """扫描文本中标准医学术语命中数 vs 错误术语残留数

    命中 >=5 个标准术语且无残留 → 1.0
    命中 >=3 个标准术语 → 0.9
    有残留混淆词 → 0.6-0.7
    几乎无标准术语 → 0.4
    """
    _init_terms()
    if not _CORRECT_TERMS:
        return 0.7  # 无法评估，给中性分

    matched = sum(1 for term in _CORRECT_TERMS if term in text)
    residual = sum(1 for err in _ERROR_TERMS if err in text)

    if matched >= 5 and residual == 0:
        return 1.0
    if matched >= 3 and residual == 0:
        return 0.9
    if residual > 0:
        # 有残留错误，根据匹配数给 0.6-0.7
        return 0.7 if matched >= 2 else 0.6
    if matched >= 1:
        return 0.8
    return 0.4


# ── 信号 3: 数值模式合理性 ──

def _score_number_validity(text: str) -> float:
    """检查文本中数值是否在生理合理范围内

    所有数值合理 → 1.0
    1个超范围 → 0.7
    2+个超范围 → 0.4
    无数值 → 0.8 (中性，不惩罚)
    """
    try:
        from validators import _extract_number_unit_pairs, _find_field_for_position
        from rule_engine import get_rule
        field_hints = get_rule("extraction.field_asr_hints", {})
    except Exception:
        return 0.8

    if not field_hints:
        return 0.8

    pairs = _extract_number_unit_pairs(text)
    if not pairs:
        return 0.8  # 无数值，中性分

    valid_count = 0
    total = 0
    for pair in pairs:
        field_id = _find_field_for_position(text, pair["start"], field_hints)
        if not field_id or field_id not in field_hints:
            continue
        total += 1
        info = field_hints[field_id]
        range_val = info.get("range", [])
        if len(range_val) != 2:
            valid_count += 1  # 无范围定义，视为合理
            continue
        min_val, max_val = range_val
        val = pair["value"]
        # 简单范围检查 (不做单位转换，因为 pairs 已经是提取到的标准单位)
        if min_val <= val <= max_val:
            valid_count += 1
        # 允许 50% 偏差
        elif val < min_val * 0.5 or val > max_val * 1.5:
            pass  # 严重超范围，不计入 valid
        else:
            valid_count += 0.5  # 轻微偏差，半分

    if total == 0:
        return 0.8

    ratio = valid_count / total
    if ratio >= 1.0:
        return 1.0
    if ratio >= 0.8:
        return 0.85
    if ratio >= 0.5:
        return 0.7
    return 0.4


# ── 信号 4: 文本结构完整性 ──

def _score_structure(text: str) -> float:
    """检查文本长度、高频模式命中、异常特征

    长度合理(50-500字) + 命中>=2高频模式 + 无异常 → 1.0
    长度合理 + 无异常 → 0.85
    有轻微异常 → 0.6
    严重异常(过短/过长/大量重复) → 0.3
    """
    text_len = len(text)

    # 严重异常检测
    if text_len < 10:
        return 0.3
    if text_len > 2000:
        return 0.3

    # 连续重复检测 (ASR典型异常)
    repeat_pattern = re.findall(r'([\u4e00-\u9fff])\1{3,}', text)
    if len(repeat_pattern) > 2:
        return 0.3

    score = 1.0

    # 长度合理性
    if text_len < 50 or text_len > 800:
        score -= 0.15

    # 高频模式命中
    try:
        from knowledge.loader import get_kb
        lm = get_kb().asr_language_model
        patterns = lm.get("ngram_language_model", {}).get("high_freq_patterns", [])
        if patterns:
            hit_count = sum(1 for p in patterns if p.get("pattern", "") in text)
            if hit_count >= 2:
                pass  # 不扣分
            elif hit_count == 1:
                score -= 0.05
            else:
                score -= 0.1
    except Exception:
        score -= 0.05  # 无法评估，轻微扣分

    # 轻微异常检测
    if len(repeat_pattern) > 0:
        score -= 0.1

    return max(0.3, min(1.0, score))


# ── 综合评估 ──

def estimate_asr_quality(text: str, exam_type: str = "腹部超声",
                         correction_stats: dict | None = None) -> dict:
    """ASR 质量综合评估

    Args:
        text: 已纠错的 ASR 文本
        exam_type: 检查类型
        correction_stats: 来自 asr_client 的纠错统计 (可选)

    Returns:
        {
            "confidence": float,      # 综合分 0-1
            "route": "fast" | "full", # 路由决策
            "signals": {              # 4个信号明细
                "correction_rate": float,
                "terminology": float,
                "number_validity": float,
                "structure": float,
            },
            "details": str,           # 决策说明
        }
    """
    config = _load_config()

    if not config.get("enabled", True):
        return {
            "confidence": 0.0,
            "route": "full",
            "signals": {},
            "details": "动态路由已禁用",
        }

    weights = config.get("weights", _DEFAULT_CONFIG["weights"])
    threshold = config.get("threshold", 0.90)

    # 计算 4 个信号
    sig_cr = _score_correction_rate(correction_stats)
    sig_tm = _score_terminology(text)
    sig_nv = _score_number_validity(text)
    sig_st = _score_structure(text)

    signals = {
        "correction_rate": sig_cr,
        "terminology": sig_tm,
        "number_validity": sig_nv,
        "structure": sig_st,
    }

    # 加权计算综合分
    if sig_cr < 0:
        # correction_stats 不可用，重新分配权重
        # 原权重: cr=0.35, tm=0.25, nv=0.25, st=0.15
        # 重分配: tm=0.36, nv=0.36, st=0.28 (按比例放大)
        w_tm = weights["terminology"] / (1 - weights["correction_rate"])
        w_nv = weights["number_validity"] / (1 - weights["correction_rate"])
        w_st = weights["structure"] / (1 - weights["correction_rate"])
        confidence = w_tm * sig_tm + w_nv * sig_nv + w_st * sig_st
        detail_mode = "3信号降级(无correction_stats)"
    else:
        confidence = (
            weights["correction_rate"] * sig_cr
            + weights["terminology"] * sig_tm
            + weights["number_validity"] * sig_nv
            + weights["structure"] * sig_st
        )
        detail_mode = "4信号完整"

    confidence = round(max(0.0, min(1.0, confidence)), 3)
    route = "fast" if confidence >= threshold else "full"

    details = (
        f"{detail_mode} | confidence={confidence} threshold={threshold} route={route} | "
        f"cr={sig_cr:.2f} tm={sig_tm:.2f} nv={sig_nv:.2f} st={sig_st:.2f}"
    )

    _log.info(f"ASR质量评估: {details}")

    return {
        "confidence": confidence,
        "route": route,
        "signals": signals,
        "details": details,
    }
