"""
Ultrasound-AI-Service — 结构化JSON日志
"""

import sys
import json
import time
import logging
from datetime import datetime, timezone
from typing import Any

from . import config


class JsonFormatter(logging.Formatter):
    """JSON 格式日志输出"""

    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        # 附加字段
        if hasattr(record, "duration_ms"):
            log_entry["duration_ms"] = record.duration_ms
        if hasattr(record, "patient_id"):
            log_entry["patient_id"] = record.patient_id
        if hasattr(record, "method"):
            log_entry["method"] = record.method
        if hasattr(record, "audit_id"):
            log_entry["audit_id"] = record.audit_id

        # 异常信息
        if record.exc_info and record.exc_info[1]:
            log_entry["exception"] = str(record.exc_info[1])

        return json.dumps(log_entry, ensure_ascii=False)


def setup_logger(name: str = "ultrasound-ai-service") -> logging.Logger:
    """创建结构化日志器"""
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    logger.setLevel(getattr(logging, config.LOG_LEVEL.upper(), logging.INFO))

    # 控制台输出(供 systemd/uvicorn 捕获)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    logger.addHandler(handler)

    # 不传播到 Root Logger
    logger.propagate = False

    return logger


# 获取一个可用的 logger 全局实例
logger = setup_logger()
