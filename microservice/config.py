"""
Ultrasound-AI-Service — 配置管理
优先级: 环境变量 > 默认值
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# 加载 .env (从项目根目录)
_project_root = Path(__file__).resolve().parents[1]
_env_file = _project_root / ".env"
if _env_file.exists():
    load_dotenv(_env_file)

# ── API Keys ──
DASHSCOPE_API_KEY: str = os.getenv("DASHSCOPE_API_KEY", "")
DEEPSEEK_API_KEY: str = os.getenv("DEEPSEEK_API_KEY", "")

# ── 服务配置 ──
SERVICE_PORT: int = int(os.getenv("ULTRASOUND_SERVICE_PORT", "8800"))
SERVICE_HOST: str = os.getenv("ULTRASOUND_SERVICE_HOST", "0.0.0.0")
LOG_LEVEL: str = os.getenv("ULTRASOUND_LOG_LEVEL", "INFO")

# ── 熔断配置 ──
LLM_TIMEOUT_SECONDS: float = float(os.getenv("LLM_TIMEOUT_SECONDS", "3.0"))
LLM_MAX_RETRIES: int = int(os.getenv("LLM_MAX_RETRIES", "2"))
CIRCUIT_BREAKER_THRESHOLD: int = int(os.getenv("CIRCUIT_BREAKER_THRESHOLD", "5"))  # 连续失败N次后熔断
CIRCUIT_BREAKER_RECOVERY: float = float(os.getenv("CIRCUIT_BREAKER_RECOVERY", "30.0"))  # 30s后尝试恢复

# ── 音频过滤配置 ──
AUDIO_MIN_DURATION: float = float(os.getenv("AUDIO_MIN_DURATION", "0.5"))  # 最短有效音频(秒)
AUDIO_MIN_SIZE: int = int(os.getenv("AUDIO_MIN_SIZE", "1024"))  # 最小文件大小(字节)

# ── 审核日志配置 ──
AUDIT_DB_PATH: Path = Path(os.getenv("AUDIT_DB_PATH", str(_project_root / "backend" / "audit.db")))

# ── 模板配置 ──
TEMPLATE_DIR: str = os.getenv("TEMPLATE_DIR", str(_project_root / "backend" / "knowledge"))
TEMPLATE_CSV: str = os.getenv("TEMPLATE_CSV", r"C:\Users\Administrator\Desktop\超声结构化报告\长沙医院模板123.csv")

# ── 调试 ──
DEBUG: bool = os.getenv("ULTRASOUND_DEBUG", "false").lower() in ("1", "true", "yes")


# ── 运行时状态 ──
class ServiceStatus:
    """服务健康状态 (单例)"""
    asr_available: bool = bool(DASHSCOPE_API_KEY)
    llm_available: bool = bool(DEEPSEEK_API_KEY)
    circuit_open: bool = False
    total_requests: int = 0
    total_failures: int = 0
    total_degraded: int = 0
