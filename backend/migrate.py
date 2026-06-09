"""
SQLite → PostgreSQL 迁移脚本

用法：
  DATABASE_URL=postgresql://user:pass@localhost:5432/ultrasound python migrate.py

说明：
- 默认读取当前 backend/ultrasound.db
- 会创建 PostgreSQL 核心 schema
- 支持重复执行：主键冲突时跳过
"""
import json
import os
import sqlite3
from pathlib import Path

import pg_db

SQLITE_PATH = Path(__file__).parent / "ultrasound.db"

TABLES = [
    "doctors",
    "patients",
    "reports",
    "audio_recordings",
    "asr_logs",
    "intent_logs",
    "match_log",
    "report_edits",
    "audit_log",
    "kb_versions",
    "template_categories",
    "api_reports",
    "api_trace_logs",
    "abcdef_trace_log",
]

JSON_COLUMNS = {"structured", "edited", "variables"}


def _sqlite_rows(conn, table):
    try:
        rows = conn.execute(f"SELECT * FROM {table}").fetchall()
        return [dict(r) for r in rows]
    except sqlite3.OperationalError:
        return []


def _pg_columns(pg_conn, table):
    rows = pg_conn.execute(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema='public' AND table_name=%s
        ORDER BY ordinal_position
        """,
        (table,),
    ).fetchall()
    return [r["column_name"] for r in rows]


def _create_compatible_pg_table(pg_conn, table, sample_row):
    """为不在核心 schema 中的 SQLite 表创建兼容 PostgreSQL 表。"""
    if not sample_row:
        return
    defs = []
    for col, value in sample_row.items():
        if col == "id":
            defs.append("id BIGINT PRIMARY KEY")
        elif col.endswith("_at") or col in {"created_at", "updated_at", "confirmed_at"}:
            defs.append(f"{col} TIMESTAMPTZ")
        elif isinstance(value, int):
            defs.append(f"{col} BIGINT")
        elif isinstance(value, float):
            defs.append(f"{col} DOUBLE PRECISION")
        else:
            defs.append(f"{col} TEXT")
    pg_conn.execute(f"CREATE TABLE IF NOT EXISTS {table} ({', '.join(defs)})")
    pg_conn.commit()


def _normalize_value(col, value):
    if value is None:
        return None
    if col in JSON_COLUMNS:
        if isinstance(value, (dict, list)):
            return json.dumps(value, ensure_ascii=False)
        if isinstance(value, str):
            s = value.strip()
            if not s:
                return "{}"
            try:
                json.loads(s)
                return s
            except Exception:
                return json.dumps({"text": s}, ensure_ascii=False)
    return value


def migrate_table(sqlite_conn, pg_conn, table):
    rows = _sqlite_rows(sqlite_conn, table)
    if not rows:
        return {"table": table, "sqlite": 0, "inserted": 0, "skipped": 0}

    pg_cols = set(_pg_columns(pg_conn, table))
    if not pg_cols:
        _create_compatible_pg_table(pg_conn, table, rows[0])
        pg_cols = set(_pg_columns(pg_conn, table))
    if not pg_cols:
        return {"table": table, "sqlite": len(rows), "inserted": 0, "skipped": len(rows), "reason": "missing_pg_table"}

    inserted = 0
    skipped = 0
    for row in rows:
        cols = [c for c in row.keys() if c in pg_cols]
        if not cols:
            skipped += 1
            continue
        placeholders = ",".join(["%s"] * len(cols))
        col_sql = ",".join(cols)
        values = [_normalize_value(c, row.get(c)) for c in cols]
        conflict = " ON CONFLICT DO NOTHING"
        try:
            pg_conn.execute(f"INSERT INTO {table} ({col_sql}) VALUES ({placeholders}){conflict}", values)
            inserted += 1
        except Exception as exc:
            pg_conn.rollback()
            skipped += 1
            print(f"[skip] {table}: {exc}")
        else:
            pg_conn.commit()
    return {"table": table, "sqlite": len(rows), "inserted": inserted, "skipped": skipped}


def main():
    if not os.getenv("DATABASE_URL"):
        raise SystemExit("DATABASE_URL 未设置")
    if not SQLITE_PATH.exists():
        raise SystemExit(f"SQLite文件不存在: {SQLITE_PATH}")

    pg_db.init_schema()
    sqlite_conn = sqlite3.connect(str(SQLITE_PATH))
    sqlite_conn.row_factory = sqlite3.Row

    results = []
    with pg_db.connection() as pg_conn:
        for table in TABLES:
            results.append(migrate_table(sqlite_conn, pg_conn, table))

    sqlite_conn.close()
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
