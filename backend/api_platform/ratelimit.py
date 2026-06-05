"""API Platform — 频率限制 (基于内存滑动窗口)"""

import time
import threading
from collections import defaultdict

from .db import rate_limit_get
from .billing import get_plan

# 内存存储: {tenant_id: {endpoint: [timestamps]}}
_window_minute: dict[int, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
_window_day: dict[int, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
_lock = threading.Lock()


def _clean_window(window: list[float], cutoff: float) -> list[float]:
    while window and window[0] < cutoff:
        window.pop(0)
    return window


def check_rate_limit(tenant_id: int, plan_id: str, endpoint: str = "*") -> tuple[bool, str]:
    """
    检查频率限制
    返回: (allowed, message)
    """
    plan = get_plan(plan_id)
    now = time.time()

    with _lock:
        # 对指定端点
        ep_min = _window_minute[tenant_id][endpoint]
        ep_day = _window_day[tenant_id][endpoint]

        # 清理过期
        _clean_window(ep_min, now - 60)
        _clean_window(ep_day, now - 86400)

        # 获取限流配置: 套餐默认值优先 (DB可能无记录，fallback到plan)
        try:
            rl = rate_limit_get(tenant_id, endpoint)
            rpm_limit = rl.get("rpm", plan["rpm"])
            rpd_limit = rl.get("rpd", plan["rpd"])
        except Exception:
            rpm_limit = plan["rpm"]
            rpd_limit = plan["rpd"]

        if len(ep_min) >= rpm_limit:
            retry = int(60 - (now - ep_min[0])) + 1
            return False, f"频率超限: 每分钟最多 {rpm_limit} 次, 请 {retry} 秒后重试"

        if len(ep_day) >= rpd_limit:
            return False, f"频率超限: 每天最多 {rpd_limit} 次"

        # 记录
        ep_min.append(now)
        ep_day.append(now)

    return True, ""


def record_request(tenant_id: int, endpoint: str):
    """记录一次请求 (用于外部计数器)"""
    pass  # 滑动窗口在 check_rate_limit 中已记录
