"""API Platform — 计费 + 套餐管理

定价策略 (v4.2, 综合按量计费):
  - 文本API: 按次计费, 配额内免费, 超配额按 overage_price/次
  - 语音API: 基础配额次数 + 前30秒免费 + 超时按秒计费
  - 时长估算: WebM 码率约 4KB/s (32kbps), 2分钟约 480KB

Version: v4.2
"""

from datetime import datetime

# ── 套餐定义 ──

PLANS = {
    "free": {
        "name": "免费版",
        "monthly_fee": 0.0,
        "monthly_quota": 100,          # 每月免费 call 次数
        "overage_price": 0,            # 超配额: free 直接拒绝
        "rpm": 5,
        "rpd": 100,
        "audio_grace_seconds": 30,     # 每次语音调用前 30 秒免费
        "audio_price_per_sec": 0.001,  # 超 30 秒后每秒 ¥0.001
    },
    "basic": {
        "name": "基础版",
        "monthly_fee": 99.0,
        "monthly_quota": 1000,
        "overage_price": 0.15,         # 超配额: 每次 ¥0.15 + 语音按秒
        "rpm": 20,
        "rpd": 2000,
        "audio_grace_seconds": 30,
        "audio_price_per_sec": 0.0008,
    },
    "pro": {
        "name": "专业版",
        "monthly_fee": 299.0,
        "monthly_quota": 5000,
        "overage_price": 0.10,
        "rpm": 60,
        "rpd": 10000,
        "audio_grace_seconds": 30,
        "audio_price_per_sec": 0.0005,
    },
}

# 调用成本估算 (人民币元 — 我方支付给 DashScope / DeepSeek 的成本)
COST_PER_AUDIO_SECOND = 0.001        # DashScope ASR 成本 ¥0.001/秒
COST_PER_1K_TOKENS_IN = 0.001        # DeepSeek input
COST_PER_1K_TOKENS_OUT = 0.002       # DeepSeek output
COST_PER_STRUCTURE_CALL = 0.015      # 纯文本结构化 (固定 LLM 成本估算)


def get_plan(plan_id: str) -> dict:
    return PLANS.get(plan_id, PLANS["free"])


def calculate_transcribe_cost(asr_seconds: float, tokens_in: int, tokens_out: int) -> dict:
    """计算语音转写+结构化单次调用的我方成本"""
    asr_cost = asr_seconds * COST_PER_AUDIO_SECOND
    llm_cost = (tokens_in / 1000) * COST_PER_1K_TOKENS_IN + (tokens_out / 1000) * COST_PER_1K_TOKENS_OUT
    total = round(asr_cost + max(llm_cost, COST_PER_STRUCTURE_CALL), 4)
    return {
        "asr_cost": round(asr_cost, 4),
        "llm_cost": round(llm_cost, 4),
        "total": total,
    }


def calculate_structure_cost(tokens_in: int, tokens_out: int) -> dict:
    """计算纯文本结构化单次调用的我方成本"""
    llm_cost = (tokens_in / 1000) * COST_PER_1K_TOKENS_IN + (tokens_out / 1000) * COST_PER_1K_TOKENS_OUT
    total = round(max(llm_cost, COST_PER_STRUCTURE_CALL), 4)
    return {
        "asr_cost": 0.0,
        "llm_cost": round(llm_cost, 4),
        "total": total,
    }


def get_audio_billed_amount(asr_seconds: float, plan_id: str) -> tuple[float, float]:
    """
    计算语音按秒阶梯计费 (前 N 秒免费 + 超时部分按秒计费)
    返回: (总费用, 免费秒数)
    例: 60秒音频, 30秒免费, 30秒×¥0.001 = ¥0.03 (免费版)
    """
    plan = get_plan(plan_id)
    grace = plan.get("audio_grace_seconds", 30)
    price = plan.get("audio_price_per_sec", 0.001)
    if asr_seconds <= grace:
        return (0.0, asr_seconds)
    billed = asr_seconds - grace
    return (round(billed * price, 4), grace)


def get_billed_amount(plan_id: str, monthly_usage_count: int, audio_extra: float = 0.0) -> float:
    """
    根据套餐和当月已用次数, 计算本次调用应向客户收取的费用
    Returns:
        -1.0: 免费版配额用完, 拒绝调用
         0.0: 套餐内 free
        >0.0: 语音超时费 + 可选超配额费
    """
    plan = get_plan(plan_id)
    quota = plan["monthly_quota"]
    if monthly_usage_count < quota:
        return audio_extra                          # 配额内: 仅收语音超时费
    if plan_id == "free":
        return -1.0                                 # 免费版超出 hard stop
    return plan["overage_price"] + audio_extra      # 超配额: overage + 语音费


def check_quota(plan_id: str, monthly_count: int) -> tuple[bool, str]:
    plan = get_plan(plan_id)
    quota = plan["monthly_quota"]
    if monthly_count < quota:
        return True, ""
    if plan_id == "free":
        return False, f"免费版月度配额({quota}次)已用完, 请升级套餐"
    return True, f"已超出套餐配额 ({quota} 次), 按 {plan['overage_price']:.2f} 元/次 + 语音时长计费"
