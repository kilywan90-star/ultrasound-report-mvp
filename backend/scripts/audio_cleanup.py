#!/usr/bin/env python3
"""
语音文件自动管理:
  - 服务器保留7天
  - 每天凌晨3点自动删除7天前的文件
  - 记录删除日志到 audit_log
"""
import os, time, json
from pathlib import Path
from datetime import datetime, timedelta

AUDIO_DIR = Path(__file__).resolve().parent / "audio_backups"
RETENTION_DAYS = 7

def clean_old_audio():
    """删除 RETENTION_DAYS 天前的音频文件, 记录删除日志"""
    if not AUDIO_DIR.exists():
        return 0

    cutoff = time.time() - (RETENTION_DAYS * 86400)
    deleted = 0
    total_size = 0
    log_entries = []

    for fpath in AUDIO_DIR.glob("*"):
        if not fpath.is_file():
            continue
        try:
            mtime = fpath.stat().st_mtime
            if mtime < cutoff:
                size = fpath.stat().st_size
                fpath.unlink()
                deleted += 1
                total_size += size
                log_entries.append({
                    "file": fpath.name,
                    "date": datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M"),
                    "size_kb": size // 1024,
                })
        except OSError:
            pass

    # 写入 audit_log
    if deleted > 0:
        try:
            import sqlite3
            conn = sqlite3.connect(str(Path(__file__).resolve().parent / "ultrasound.db"))
            conn.execute(
                "INSERT INTO audit_log (action, detail, operator, created_at) VALUES (?,?,?,?)",
                ("audio_cleanup",
                 json.dumps({"deleted_files": deleted, "total_size_kb": total_size // 1024, "files": log_entries[:5]},
                           ensure_ascii=False),
                 "system",
                 datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
            )
            conn.commit()
            conn.close()
        except Exception:
            pass

    print(f"[audio-cleanup] {datetime.now().strftime('%Y-%m-%d %H:%M')}: deleted {deleted} files ({total_size//1024} KB)")
    return deleted


def get_audio_stats():
    """获取当前音频文件统计"""
    if not AUDIO_DIR.exists():
        return {"count": 0, "total_size_kb": 0, "oldest": None, "newest": None}

    files = [(f.stat().st_mtime, f.stat().st_size, f.name) for f in AUDIO_DIR.glob("*") if f.is_file()]
    if not files:
        return {"count": 0, "total_size_kb": 0, "oldest": None, "newest": None}

    files.sort()
    return {
        "count": len(files),
        "total_size_kb": sum(s for _, s, _ in files) // 1024,
        "oldest": datetime.fromtimestamp(files[0][0]).strftime("%Y-%m-%d %H:%M"),
        "newest": datetime.fromtimestamp(files[-1][0]).strftime("%Y-%m-%d %H:%M"),
    }


if __name__ == "__main__":
    stats = get_audio_stats()
    print(f"Before cleanup: {stats['count']} files, {stats['total_size_kb']} KB")
    if stats['oldest']:
        print(f"  Oldest: {stats['oldest']}")
        print(f"  Newest: {stats['newest']}")

    n = clean_old_audio()

    stats2 = get_audio_stats()
    print(f"After cleanup: {stats2['count']} files, {stats2['total_size_kb']} KB")
