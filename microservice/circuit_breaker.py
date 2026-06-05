"""
Ultrasound-AI-Service — 熔断器
LLM 调用超过 TIMEOUT 自动降级到规则引擎
连续失败达阈值→完全熔断，30秒后尝试恢复
"""

import time, threading
from . import config
from .logger import logger


class CircuitBreaker:
    """线程安全的熔断器"""

    def __init__(self, threshold: int = 5, recovery_seconds: float = 30.0):
        self.threshold = threshold or config.CIRCUIT_BREAKER_THRESHOLD
        self.recovery_seconds = recovery_seconds or config.CIRCUIT_BREAKER_RECOVERY
        self._failure_count = 0
        self._last_failure_time = 0.0
        self._open_time = 0.0
        self._state = "closed"  # closed | open | half_open
        self._lock = threading.Lock()

    @property
    def is_open(self) -> bool:
        with self._lock:
            if self._state == "open":
                if time.time() - self._open_time > self.recovery_seconds:
                    self._state = "half_open"
                    logger.info("Circuit breaker: half_open (recovery attempt)")
                    return False
                return True
            return False

    def record_success(self):
        with self._lock:
            self._failure_count = 0
            self._state = "closed"

    def record_failure(self):
        with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.time()
            config.ServiceStatus.total_failures += 1
            if self._failure_count >= self.threshold:
                self._state = "open"
                self._open_time = time.time()
                logger.warning(
                    f"Circuit breaker: OPEN (failures={self._failure_count}/{self.threshold})"
                )

    def record_degraded(self):
        """记录一次降级成功(熔断器open但规则兜底成功)"""
        with self._lock:
            config.ServiceStatus.total_degraded += 1

    def execute(self, func, fallback_func=None, timeout: float = None):
        """
        执行函数，超时/失败时自动fallback
        返回: (result, degraded: bool)
        """
        timeout = timeout or config.LLM_TIMEOUT_SECONDS

        if self.is_open:
            logger.warning("Circuit breaker open — using fallback directly")
            if fallback_func:
                result = fallback_func()
                self.record_degraded()
                return result, True
            raise RuntimeError("Circuit breaker open, no fallback available")

        try:
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(func)
                result = future.result(timeout=timeout)
            self.record_success()
            return result, False
        except (concurrent.futures.TimeoutError, TimeoutError):
            logger.warning(f"LLM timeout after {timeout}s — degraded")
            self.record_failure()
            config.ServiceStatus.total_degraded += 1
            if fallback_func:
                return fallback_func(), True
            raise
        except Exception as e:
            logger.warning(f"LLM error: {e} — degraded")
            self.record_failure()
            config.ServiceStatus.total_degraded += 1
            if fallback_func:
                return fallback_func(), True
            raise


# 全局熔断器实例
circuit_breaker = CircuitBreaker()
