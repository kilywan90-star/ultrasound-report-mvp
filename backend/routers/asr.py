"""
统一 ASR 路由

目标：
- 所有前端录音/上传统一走 /api/asr/transcribe
- 音频先标准化为 16kHz mono wav
- DashScope 文件转写优先
- 本地 Whisper/FunASR/SenseVoice 预留兜底
- 医学纠错、质量评分、日志入库统一返回
"""
import asyncio
import json
import logging
import os
import shutil
import subprocess
import time
import uuid
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from asr_correction import correct_ASR_text
from asr_service import asr
from database import get_db

router = APIRouter(prefix="/api/asr", tags=["ASR"])

AUDIO_DIR = Path(__file__).resolve().parent.parent / "recordings"
AUDIO_DIR.mkdir(exist_ok=True)

DASHSCOPE_API_KEY = os.getenv("DASHSCOPE_API_KEY", "")
ASR_PRIMARY = os.getenv("ASR_PRIMARY", "dashscope").strip().lower()
ASR_FALLBACK = os.getenv("ASR_FALLBACK", "whisper").strip().lower()


def _safe_suffix(filename: str) -> str:
    suffix = Path(filename or "audio.webm").suffix.lower()
    if suffix in {".webm", ".wav", ".mp3", ".m4a", ".ogg", ".aac", ".flac"}:
        return suffix
    return ".webm"


def _save_upload(content: bytes, filename: str) -> Path:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    uid = uuid.uuid4().hex[:8]
    path = AUDIO_DIR / f"{ts}_{uid}{_safe_suffix(filename)}"
    path.write_bytes(content)
    return path


def _normalize_audio(src: Path) -> tuple[Path, list[str]]:
    """转为 16kHz mono wav。若 ffmpeg 不存在或失败，则回退原文件。"""
    warnings = []
    if not shutil.which("ffmpeg"):
        warnings.append("ffmpeg未安装，跳过音频标准化")
        return src, warnings
    dst = src.with_suffix(".16k.wav")
    cmd = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-i", str(src),
        "-ac", "1",
        "-ar", "16000",
        "-f", "wav",
        str(dst),
    ]
    try:
        subprocess.run(cmd, check=True, timeout=30)
        if dst.exists() and dst.stat().st_size > 44:
            return dst, warnings
        warnings.append("ffmpeg转换后文件为空，使用原始音频")
    except Exception as exc:
        warnings.append(f"ffmpeg转换失败，使用原始音频: {exc}")
    return src, warnings


def _score_quality(text: str, duration_seconds: float = 0.0) -> float:
    if not text:
        return 0.0
    score = 0.55
    medical_terms = [
        "肝脏", "胆囊", "胰腺", "脾脏", "肾", "甲状腺", "乳腺", "子宫", "卵巢",
        "前列腺", "回声", "结节", "囊肿", "钙化", "强回声", "低回声", "无回声",
        "CDFI", "血流", "内径", "包膜", "声影", "胆总管", "淋巴结", "BI-RADS", "TI-RADS",
    ]
    hits = sum(1 for term in medical_terms if term in text)
    score += min(0.25, hits * 0.03)
    if any(ch.isdigit() for ch in text):
        score += 0.08
    if len(text) >= 8:
        score += 0.08
    if duration_seconds and len(text) / max(duration_seconds, 1) < 0.5:
        score -= 0.15
    if any(bad in text for bad in ["字幕", "谢谢", "音乐", "哈哈"]):
        score -= 0.15
    return round(max(0.0, min(score, 0.99)), 2)


def _looks_invalid_asr(text: str) -> bool:
    """过滤噪声导致的重复字/无意义识别。"""
    if not text:
        return True
    clean = text.strip()
    if len(clean) < 2:
        return True
    if "�" in clean or "�" in clean:
        return True

    # 单字重复，如“轻轻轻轻...”。保留少量医学符号后判断。
    normalized = clean.replace("。", "").replace("，", "").replace(",", "").replace(".", "").replace(" ", "")
    unique_chars = set(normalized)
    if len(normalized) >= 12 and len(unique_chars) <= 3:
        return True

    # 高频短语重复，如“腹部。腹部。腹部...”。
    import re
    tokens = [t for t in re.split(r"[。！？!?，,\s]+", clean) if t]
    if len(tokens) >= 12:
        counts = {}
        for token in tokens:
            counts[token] = counts.get(token, 0) + 1
        top_token, top_count = max(counts.items(), key=lambda item: item[1])
        if top_count >= 10 and top_count / len(tokens) >= 0.55 and len(top_token) <= 6:
            return True

    # 重复 n 字片段，如“嗯嗯嗯嗯”或“腹部腹部腹部”。
    for n in range(1, 7):
        if len(normalized) >= n * 8:
            token = normalized[:n]
            repeat_len = n * (len(normalized) // n)
            if token and token * (repeat_len // n) == normalized[:repeat_len]:
                return True

    invalid_phrases = {"谢谢观看", "字幕由", "音乐", "轻轻"}
    if any(p in clean for p in invalid_phrases) and not any(m in clean for m in ["肝", "胆", "肾", "甲状腺", "乳腺", "回声"]):
        return True
    return False


async def _dashscope_file_asr(audio_path: Path) -> str:
    """DashScope 主识别路径：优先使用 qwen3-asr-flash 多模态本地音频。"""
    if not DASHSCOPE_API_KEY:
        return ""
    try:
        import dashscope
    except Exception as exc:
        logging.warning("DashScope SDK不可用: %s", exc)
        return ""

    def _call() -> str:
        dashscope.api_key = DASHSCOPE_API_KEY
        response = dashscope.MultiModalConversation.call(
            model="qwen3-asr-flash",
            messages=[{"role": "user", "content": [{"audio": str(audio_path)}]}],
            api_key=DASHSCOPE_API_KEY,
        )
        if getattr(response, "status_code", None) != 200:
            logging.warning("DashScope qwen3-asr-flash失败: status=%s message=%s", getattr(response, "status_code", None), getattr(response, "message", None))
            return ""
        try:
            content = response.output.choices[0].message.content
            if isinstance(content, list):
                return "".join(c.get("text", "") if isinstance(c, dict) else str(c) for c in content).strip()
            return str(content or "").strip()
        except Exception as exc:
            logging.warning("DashScope qwen3-asr-flash响应解析失败: %s", exc)
            return ""

    try:
        return await asyncio.wait_for(asyncio.to_thread(_call), timeout=120)
    except Exception as exc:
        logging.warning("DashScope ASR异常: %s", exc)
        return ""


async def _local_fallback_asr(audio_path: Path, content: bytes, exam_type: str) -> tuple[str, str, float]:
    """本地兜底。当前使用现有 whisper 服务，保留 FunASR/SenseVoice 扩展点。"""
    engine = ASR_FALLBACK
    if engine in {"sensevoice", "funasr"}:
        # 预留扩展：后续可在这里调用独立本地服务，例如 http://127.0.0.1:10095/asr
        service_url = os.getenv("LOCAL_ASR_URL", "").strip()
        if service_url:
            # 为避免引入额外依赖，这里先不默认启用 HTTP 适配器
            logging.info("LOCAL_ASR_URL 已配置但尚未启用: %s", service_url)
    start = time.time()
    result = await asyncio.to_thread(asr.transcribe, content, "zh", exam_type)
    elapsed = time.time() - start
    return result.get("text", "").strip(), "whisper", float(result.get("quality_score", 0.5) or 0.5), elapsed


def _log_asr(filename: str, path: Path, file_size: int, raw: str, corrected: str, source: str, quality: float, elapsed: float, doctor: str) -> None:
    conn = get_db()
    try:
        cur = conn.execute(
            """INSERT INTO audio_recordings(filename,filepath,file_size,doctor,status)
               VALUES(?,?,?,?,'processed')""",
            (filename, str(path), file_size, doctor),
        )
        audio_id = getattr(cur, "lastrowid", None)
        conn.execute(
            """INSERT INTO asr_logs(audio_file,raw_text,corrected_text,source,quality_score,
               elapsed_seconds,doctor,report_id)
               VALUES(?,?,?,?,?,?,?,?)""",
            (filename, raw, corrected, source, quality, elapsed, doctor, ""),
        )
        conn.commit()
    except Exception as exc:
        logging.warning("ASR日志写入失败: %s", exc)
        conn.rollback()
    finally:
        conn.close()


@router.post("/transcribe")
async def transcribe_unified(
    file: UploadFile = File(...),
    doctor: str = Form(""),
    exam_type: str = Form("腹部超声"),
    run_structure: bool = Form(False),
):
    if not file.filename:
        raise HTTPException(400, "文件名为空")
    content = await file.read()
    if len(content) == 0:
        raise HTTPException(400, "文件为空")
    if len(content) > 50 * 1024 * 1024:
        raise HTTPException(413, "音频文件过大，最大50MB")

    src_path = _save_upload(content, file.filename)
    normalized_path, warnings = _normalize_audio(src_path)
    start = time.time()

    raw_text = ""
    source = ""
    fallback_used = False
    fallback_quality = 0.0

    if ASR_PRIMARY == "dashscope":
        raw_text = await _dashscope_file_asr(normalized_path)
        if raw_text:
            source = "dashscope"

    if not raw_text:
        fallback_used = True
        raw_text, source, fallback_quality, _fallback_elapsed = await _local_fallback_asr(normalized_path, content, exam_type)

    elapsed = time.time() - start
    corrected = correct_ASR_text(raw_text.strip()) if raw_text else ""
    invalid_asr = _looks_invalid_asr(corrected or raw_text)
    if invalid_asr:
        warnings.append("识别结果疑似噪声或无效语音，请重新录制")
        corrected = ""
    quality = 0.0 if invalid_asr else (fallback_quality if fallback_quality else _score_quality(corrected or raw_text, elapsed))

    _log_asr(src_path.name, src_path, len(content), raw_text, corrected, source or "none", quality, elapsed, doctor)

    response = {
        "success": bool(corrected),
        "text": corrected,
        "raw_text": raw_text,
        "corrected_text": corrected,
        "source": source or "none",
        "fallback_used": fallback_used,
        "quality_score": quality,
        "elapsed_seconds": round(elapsed, 2),
        "duration_seconds": None,
        "audio_file": src_path.name,
        "audio_path": str(src_path),
        "normalized_audio": str(normalized_path),
        "warnings": warnings,
    }

    if run_structure and corrected:
        from pipeline import pipeline as pl
        if pl:
            try:
                response["structure"] = pl.process_and_save(corrected, doctor)
            except Exception as exc:
                response["warnings"].append(f"结构化失败: {exc}")

    return response


@router.post("/upload")
async def upload_compat(file: UploadFile = File(...), doctor: str = Form(""), exam_type: str = Form("腹部超声")):
    """兼容旧前端：转发到统一接口。"""
    return await transcribe_unified(file=file, doctor=doctor, exam_type=exam_type, run_structure=False)
