"""
Ultrasound-AI-Service — 音频质量过滤
检查音频有效性: 时长/大小/静音检测
"""

import struct
from . import config
from .logger import logger


def check_audio_validity(audio_bytes: bytes, sample_rate: int = 16000) -> dict:
    """
    检查音频是否有效
    返回: {"is_valid": bool, "duration": float, "reason": str}
    """
    # 1. 大小检查
    if len(audio_bytes) < config.AUDIO_MIN_SIZE:
        return {"is_valid": False, "duration": 0, "reason": f"音频文件过小({len(audio_bytes)}B < {config.AUDIO_MIN_SIZE}B)"}

    # 2. 时长估算 (假设 16kHz, 16bit, mono = 32000字节/秒)
    estimated_duration = len(audio_bytes) / (sample_rate * 2)
    if estimated_duration < config.AUDIO_MIN_DURATION:
        return {"is_valid": False, "duration": round(estimated_duration, 2),
                "reason": f"音频时长过短({estimated_duration:.1f}s < {config.AUDIO_MIN_DURATION}s)"}

    # 3. 静音检测 (简单RMS能量检查)
    try:
        rms = _compute_rms(audio_bytes)
        if rms < 50:  # 非常低的能量 = 大概率静音
            return {"is_valid": False, "duration": round(estimated_duration, 2),
                    "reason": f"音频能量过低(可能为静音文件, RMS={rms:.0f})"}
    except Exception:
        pass  # 解析失败不阻断, 让ASR自己去判断

    return {"is_valid": True, "duration": round(estimated_duration, 2), "reason": ""}


def _compute_rms(audio_bytes: bytes) -> float:
    """计算16位PCM音频的RMS能量"""
    if not audio_bytes:
        return 0.0
    # 跳过WAV header (44字节) if present
    offset = 44 if audio_bytes[:4] == b'RIFF' else 0
    data = audio_bytes[offset:]
    if len(data) < 2:
        return 0.0

    count = len(data) // 2
    samples = struct.unpack(f"{count}h", data[:count * 2])
    sum_sq = sum(s * s for s in samples)
    rms = (sum_sq / count) ** 0.5
    return rms
