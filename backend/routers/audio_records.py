"""
语音档案 / 全链路追踪 API

提供：
- 录音文件列表
- 录音详情（ASR日志、意图、匹配、报告）
- 原始/标准化音频回听
- 保存目录状态
"""
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from database import get_db

router = APIRouter(prefix="/api/audio-records", tags=["语音档案"])

AUDIO_DIR = Path(__file__).resolve().parent.parent / "recordings"


def _row_to_dict(row):
    return dict(row) if row else None


def _safe_audio_path(filename: str) -> Path:
    name = Path(filename).name
    path = AUDIO_DIR / name
    try:
        path.resolve().relative_to(AUDIO_DIR.resolve())
    except Exception:
        raise HTTPException(400, "非法文件名")
    if not path.exists() or not path.is_file():
        raise HTTPException(404, "音频文件不存在")
    return path


def _infer_normalized_path(filename: str) -> str:
    path = AUDIO_DIR / Path(filename).name
    wav = path.with_suffix(".16k.wav")
    return str(wav) if wav.exists() else ""


def _media_type(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".wav":
        return "audio/wav"
    if suffix == ".mp3":
        return "audio/mpeg"
    if suffix == ".ogg":
        return "audio/ogg"
    if suffix == ".webm":
        return "audio/webm"
    if suffix == ".m4a":
        return "audio/mp4"
    return "application/octet-stream"


@router.get("/storage")
def storage_status():
    AUDIO_DIR.mkdir(exist_ok=True)
    total_bytes = 0
    total_files = 0
    for p in AUDIO_DIR.glob("*"):
        if p.is_file():
            total_files += 1
            total_bytes += p.stat().st_size
    return {
        "directory": str(AUDIO_DIR),
        "exists": AUDIO_DIR.exists(),
        "total_files": total_files,
        "total_bytes": total_bytes,
        "total_mb": round(total_bytes / 1024 / 1024, 2),
    }


@router.get("")
def list_audio_records(limit: int = 100, offset: int = 0, source: str = "", status: str = "", q: str = ""):
    conn = get_db()
    sql = "SELECT * FROM audio_recordings WHERE 1=1"
    params = []
    if status:
        sql += " AND status=?"
        params.append(status)
    if q:
        sql += " AND (filename LIKE ? OR doctor LIKE ?)"
        params.extend([f"%{q}%", f"%{q}%"])
    sql += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])
    rows = conn.execute(sql, params).fetchall()
    records = []
    for row in rows:
        item = dict(row)
        filename = item.get("filename", "")
        asr = conn.execute(
            "SELECT * FROM asr_logs WHERE audio_file=? ORDER BY id DESC LIMIT 1",
            (filename,),
        ).fetchone()
        if asr:
            asr_dict = dict(asr)
            item["asr"] = {
                "source": asr_dict.get("source", ""),
                "quality_score": asr_dict.get("quality_score", 0),
                "elapsed_seconds": asr_dict.get("elapsed_seconds", 0),
                "raw_text_preview": (asr_dict.get("raw_text") or "")[:80],
                "corrected_text_preview": (asr_dict.get("corrected_text") or "")[:80],
                "created_at": asr_dict.get("created_at", ""),
            }
            if source and asr_dict.get("source") != source:
                continue
        else:
            item["asr"] = None
            if source:
                continue
        item["normalized_path"] = _infer_normalized_path(filename)
        item["play_url"] = f"/api/audio-records/{item['id']}/play?kind=original"
        item["normalized_play_url"] = f"/api/audio-records/{item['id']}/play?kind=normalized"
        records.append(item)
    total = conn.execute("SELECT COUNT(*) AS n FROM audio_recordings").fetchone()["n"]
    conn.close()
    return {"records": records, "total": total, "limit": limit, "offset": offset}


@router.get("/{record_id}")
def get_audio_record(record_id: int):
    conn = get_db()
    audio = conn.execute("SELECT * FROM audio_recordings WHERE id=?", (record_id,)).fetchone()
    if not audio:
        conn.close()
        raise HTTPException(404, "录音不存在")
    audio_dict = dict(audio)
    filename = audio_dict.get("filename", "")

    asr_logs = [dict(r) for r in conn.execute(
        "SELECT * FROM asr_logs WHERE audio_file=? ORDER BY id DESC", (filename,)
    ).fetchall()]
    intent_logs = []
    match_logs = []
    reports = []
    report_id = ""
    if asr_logs:
        report_id = asr_logs[0].get("report_id") or ""
    if report_id:
        intent_logs = [dict(r) for r in conn.execute(
            "SELECT * FROM intent_logs WHERE report_id=? ORDER BY id DESC", (report_id,)
        ).fetchall()]
        match_logs = [dict(r) for r in conn.execute(
            "SELECT * FROM match_log WHERE report_id=? ORDER BY id DESC", (report_id,)
        ).fetchall()]
        reports = [dict(r) for r in conn.execute(
            "SELECT * FROM reports WHERE id=?", (report_id,)
        ).fetchall()]

    conn.close()
    audio_dict["normalized_path"] = _infer_normalized_path(filename)
    audio_dict["play_url"] = f"/api/audio-records/{record_id}/play?kind=original"
    audio_dict["normalized_play_url"] = f"/api/audio-records/{record_id}/play?kind=normalized"
    return {
        "audio": audio_dict,
        "asr_logs": asr_logs,
        "intent_logs": intent_logs,
        "match_logs": match_logs,
        "reports": reports,
    }


@router.get("/{record_id}/play")
def play_audio(record_id: int, kind: Literal["original", "normalized"] = "original"):
    conn = get_db()
    row = conn.execute("SELECT * FROM audio_recordings WHERE id=?", (record_id,)).fetchone()
    conn.close()
    if not row:
        raise HTTPException(404, "录音不存在")
    filename = dict(row).get("filename", "")
    if kind == "normalized":
        original = _safe_audio_path(filename)
        normalized = original.with_suffix(".16k.wav")
        if not normalized.exists():
            raise HTTPException(404, "标准化音频不存在")
        path = normalized
    else:
        path = _safe_audio_path(filename)
    return FileResponse(path, media_type=_media_type(path), filename=path.name)


@router.get("/{record_id}/download")
def download_audio(record_id: int, kind: Literal["original", "normalized"] = "original"):
    return play_audio(record_id, kind)
