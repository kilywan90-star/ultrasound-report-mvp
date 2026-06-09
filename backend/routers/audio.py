"""
超声语音报告系统 - 音频上传/转写路由
(从 main.py 拆出的内联路由)
"""
import os, re, uuid, logging
from datetime import datetime
from pathlib import Path
from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse

import db

router = APIRouter(tags=["音频"])

AUDIO_DIR = Path(__file__).resolve().parent.parent / "audio_backups"
AUDIO_DIR.mkdir(exist_ok=True)

# 录音文件也监听recordings目录
RECORDINGS_DIR = Path(__file__).resolve().parent.parent / "recordings"
RECORDINGS_DIR.mkdir(exist_ok=True)


@router.post("/api/audio/upload")
async def audio_upload(file: UploadFile = File(...)):
    """上传原始录音到磁盘，返回 audio_id 供回放"""
    audio_bytes = await file.read()
    if len(audio_bytes) < 1024:
        raise HTTPException(400, "音频文件过小")
    if len(audio_bytes) > 50 * 1024 * 1024:
        raise HTTPException(400, "音频文件过大")

    audio_id = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
    suffix = Path(file.filename).suffix or ".webm"
    fname = f"{audio_id}{suffix}"
    fpath = AUDIO_DIR / fname

    with open(fpath, "wb") as f:
        f.write(audio_bytes)

    return {"success": True, "audio_id": audio_id, "filename": fname, "size": len(audio_bytes)}


@router.get("/api/audio/{audio_id}")
async def audio_playback(audio_id: str):
    """回放原始录音"""
    if not re.fullmatch(r'[A-Za-z0-9_]+', audio_id):
        raise HTTPException(400, "audio_id格式无效")
    # 先查recordings目录
    matches = list(RECORDINGS_DIR.glob(f"{audio_id}.*"))
    if not matches:
        matches = list(AUDIO_DIR.glob(f"{audio_id}.*"))
    if not matches:
        raise HTTPException(404, "音频文件不存在")
    return FileResponse(matches[0])


@router.get("/api/audio/{audio_id}/download")
async def audio_download(audio_id: str):
    """下载原始录音到本机"""
    if not re.fullmatch(r'[A-Za-z0-9_]+', audio_id):
        raise HTTPException(400, "audio_id格式无效")
    matches = list(RECORDINGS_DIR.glob(f"{audio_id}.*"))
    if not matches:
        matches = list(AUDIO_DIR.glob(f"{audio_id}.*"))
    if not matches:
        raise HTTPException(404, "音频文件不存在")
    fpath = matches[0]
    return FileResponse(
        fpath,
        media_type="application/octet-stream",
        filename=fpath.name,
        headers={"Content-Disposition": f"attachment; filename={fpath.name}"}
    )


@router.post("/api/transcribe")
async def transcribe(file: UploadFile = File(...)):
    """上传音频，返回转写文本 + audio_id"""
    if not file.filename:
        raise HTTPException(400, "文件格式不识别")
    audio_bytes = await file.read()
    if len(audio_bytes) < 1024:
        raise HTTPException(400, "音频文件过小")
    if len(audio_bytes) > 50 * 1024 * 1024:
        raise HTTPException(400, "音频文件过大")

    # 备份: 文件名格式 YYYYMMDDHH0001 (.webm/.wav)
    suffix = Path(file.filename).suffix or ".wav"
    now = datetime.now()
    prefix = now.strftime("%Y%m%d%H")
    existing = sorted(AUDIO_DIR.glob(f"{prefix}*{suffix}"))
    seq = len(existing) + 1
    fname = f"{prefix}{seq:04d}{suffix}"
    backup_path = AUDIO_DIR / fname
    while backup_path.exists():
        seq += 1
        fname = f"{prefix}{seq:04d}{suffix}"
        backup_path = AUDIO_DIR / fname
    audio_id = fname.rsplit(".", 1)[0]
    try:
        with open(backup_path, "wb") as f:
            f.write(audio_bytes)
    except OSError:
        backup_path = None
        audio_id = None

    # 转写
    try:
        from asr_client import _load_hotwords, transcribe_audio
        hw_count = len(_load_hotwords())
        result = await transcribe_audio(audio_bytes)
        logging.info(f"ASR转写成功: 热词{hw_count}个, 原始{len(result['raw'])}字, 纠错{len(result['text'])}字")
    except Exception as e:
        raise HTTPException(500, f"语音识别失败: {e}")

    return {
        "success": True, "raw_text": result["raw"], "text": result["text"],
        "audio_id": audio_id,
        "correction_stats": result.get("correction_stats")
    }
