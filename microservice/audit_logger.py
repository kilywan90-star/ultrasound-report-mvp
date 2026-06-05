"""
Ultrasound-AI-Service — 异步审计日志
将每次请求的完整流水线结果写入 audit.db
"""

import json, hashlib, uuid
from datetime import datetime
from pathlib import Path
import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor

from .logger import logger

# 专用线程池(避免阻塞主线程)
_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="audit")

# 数据库路径
from .config import AUDIT_DB_PATH

# 线程本地连接
_local = threading.local()


def _get_conn() -> sqlite3.Connection:
    if not hasattr(_local, "conn") or _local.conn is None:
        AUDIT_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        _local.conn = sqlite3.connect(str(AUDIT_DB_PATH), check_same_thread=False)
        _local.conn.row_factory = sqlite3.Row
        _local.conn.execute("PRAGMA journal_mode=WAL")
        _local.conn.execute("PRAGMA synchronous=NORMAL")
        _local.conn.execute("PRAGMA cache_size=-8000")
    return _local.conn


def init_audit_db():
    """建表 (幂等)"""
    c = _get_conn()
    c.executescript("""
        CREATE TABLE IF NOT EXISTS audit_log (
            id              TEXT PRIMARY KEY,
            request_type    TEXT NOT NULL CHECK(request_type IN ('transcribe','structure')),
            patient_context TEXT,
            audio_hash      TEXT,
            audio_size      INTEGER,
            audio_duration  REAL,
            raw_text        TEXT,
            corrected_text  TEXT,
            study_see       TEXT,
            study_hint      TEXT,
            template_used   TEXT,
            method          TEXT,
            confidence      REAL,
            warnings        TEXT,
            validation      TEXT,
            degraded        INTEGER DEFAULT 0,
            elapsed_ms      REAL,
            created_at      TEXT NOT NULL DEFAULT (datetime('now','localtime'))
        );

        CREATE INDEX IF NOT EXISTS idx_audit_created ON audit_log(created_at);
        CREATE INDEX IF NOT EXISTS idx_audit_template ON audit_log(template_used);
    """)


def _write_log(entry: dict):
    """内部同步写入"""
    try:
        c = _get_conn()
        c.execute("""
            INSERT INTO audit_log (
                id, request_type, patient_context, audio_hash, audio_size, audio_duration,
                raw_text, corrected_text, study_see, study_hint, template_used,
                method, confidence, warnings, validation, degraded, elapsed_ms
            ) VALUES (
                :id, :request_type, :patient_context, :audio_hash, :audio_size, :audio_duration,
                :raw_text, :corrected_text, :study_see, :study_hint, :template_used,
                :method, :confidence, :warnings, :validation, :degraded, :elapsed_ms
            )
        """, entry)
        c.commit()
    except Exception as e:
        logger.error(f"Audit write error: {e}")


def log_request_async(
    request_type: str,
    patient_context: dict | None = None,
    audio_bytes: bytes | None = None,
    audio_duration: float = 0.0,
    raw_text: str = "",
    corrected_text: str = "",
    study_see: str = "",
    study_hint: list | None = None,
    template_used: str = "",
    method: str = "",
    confidence: float = 0.0,
    warnings: list | None = None,
    validation_issues: list | None = None,
    degraded: bool = False,
    elapsed_ms: float = 0.0,
) -> str:
    """
    异步写入审计日志, 返回 audit_id
    """
    audit_id = str(uuid.uuid4())

    entry = {
        "id": audit_id,
        "request_type": request_type,
        "patient_context": json.dumps(patient_context, ensure_ascii=False) if patient_context else None,
        "audio_hash": hashlib.sha256(audio_bytes).hexdigest() if audio_bytes else None,
        "audio_size": len(audio_bytes) if audio_bytes else None,
        "audio_duration": round(audio_duration, 2) if audio_duration else None,
        "raw_text": raw_text[:1000] if raw_text else "",
        "corrected_text": corrected_text[:1000] if corrected_text else "",
        "study_see": study_see[:2000] if study_see else "",
        "study_hint": json.dumps(study_hint, ensure_ascii=False)[:1000] if study_hint else "",
        "template_used": template_used,
        "method": method,
        "confidence": round(confidence, 3),
        "warnings": json.dumps(warnings, ensure_ascii=False) if warnings else None,
        "validation": json.dumps(validation_issues, ensure_ascii=False) if validation_issues else None,
        "degraded": 1 if degraded else 0,
        "elapsed_ms": round(elapsed_ms, 1),
    }

    _executor.submit(_write_log, entry)
    return audit_id


# 启动时初始化
init_audit_db()
