"""API Platform — 计费 + 套餐管理"""

from datetime import datetime

# ── 套餐定义 ──

PLANS = {
    "free": {
        "name": "免费版",
        "monthly_fee": 0.0,
        "monthly_quota": 100,
        "overage_price": 0,
        "rpm": 5,
        "rpd": 100,
    },
    "basic": {
        "name": "基础版",
        "monthly_fee": 99.0,
        "monthly_quota": 1000,
        "overage_price": 0.15,
        "rpm": 20,
        "rpd": 2000,
    },
    "pro": {
        "name": "专业版",
        "monthly_fee": 299.0,
        "monthly_quota": 5000,
        "overage_price": 0.10,
        "rpm": 60,
        "rpd": 10000,
    },
}

# 调用成本估算 (人民币元)
COST_PER_AUDIO_SECOND = 0.001        # DashScope ASR
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


def get_billed_amount(plan_id: str, monthly_usage_count: int, is_transcribe: bool = True) -> float:
    """根据套餐和当月已用次数, 计算本次调用应向客户收取的费用"""
    plan = get_plan(plan_id)
    quota = plan["monthly_quota"]
    if monthly_usage_count < quota:
        return 0.0  # 套餐内免费
    if plan_id == "free":
        return -1.0  # 免费版超量不允许调用, 返回负数表示拒绝
    return plan["overage_price"]


def check_quota(plan_id: str, monthly_count: int) -> tuple[bool, str]:
    """
    检查套餐配额
    返回: (allowed, message)
    """
    plan = get_plan(plan_id)
    quota = plan["monthly_quota"]
    if monthly_count < quota:
        return True, ""
    if plan_id == "free":
        return False, f"免费版月度配额({quota}次)已用完, 请升级套餐"
    return True, f"已超出套餐配额, 按 {plan['overage_price']:.2f} 元/次 计费"
