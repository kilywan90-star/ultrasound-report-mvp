"""
PostgreSQL 数据库连接层
- 通过 DATABASE_URL 启用
- 使用 psycopg 连接池
- 保持与 database.py 的 get_db() 调用习惯兼容
"""
import os
from contextlib import contextmanager
from typing import Iterator

try:
    import psycopg
    from psycopg.rows import dict_row
    from psycopg_pool import ConnectionPool
except Exception:  # pragma: no cover
    psycopg = None
    dict_row = None
    ConnectionPool = None

DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
_pool = None


def enabled() -> bool:
    return bool(DATABASE_URL and psycopg and ConnectionPool)


def _pool_instance():
    global _pool
    if not enabled():
        raise RuntimeError("PostgreSQL 未启用：请设置 DATABASE_URL 并安装 psycopg[binary,pool]")
    if _pool is None:
        _pool = ConnectionPool(
            conninfo=DATABASE_URL,
            kwargs={"row_factory": dict_row},
            min_size=1,
            max_size=int(os.getenv("PG_POOL_MAX", "10")),
            open=True,
        )
    return _pool


@contextmanager
def connection() -> Iterator[object]:
    pool = _pool_instance()
    with pool.connection() as conn:
        yield conn


def init_schema() -> None:
    """创建核心表。迁移脚本会负责补充数据。"""
    with connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS doctors (
                id BIGSERIAL PRIMARY KEY,
                name TEXT UNIQUE NOT NULL,
                department TEXT DEFAULT '超声科',
                title TEXT DEFAULT '',
                employee_id TEXT DEFAULT '',
                created_at TIMESTAMPTZ DEFAULT now(),
                updated_at TIMESTAMPTZ DEFAULT now()
            );
            CREATE TABLE IF NOT EXISTS patients (
                id BIGSERIAL PRIMARY KEY,
                name TEXT NOT NULL,
                sex TEXT DEFAULT '',
                gender TEXT DEFAULT '',
                age INTEGER DEFAULT 0,
                age_unit TEXT DEFAULT '岁',
                outpatient_no TEXT DEFAULT '',
                outpatient_id TEXT DEFAULT '',
                inpatient_no TEXT DEFAULT '',
                inpatient_id TEXT DEFAULT '',
                dept_name TEXT DEFAULT '',
                department TEXT DEFAULT '',
                phone TEXT DEFAULT '',
                id_card TEXT DEFAULT '',
                bed_no TEXT DEFAULT '',
                exam_no TEXT DEFAULT '',
                exam_type TEXT DEFAULT '超声',
                exam_part TEXT DEFAULT '',
                clinical_diag TEXT DEFAULT '',
                tenant_id INTEGER,
                status TEXT DEFAULT '待检',
                created_at TIMESTAMPTZ DEFAULT now(),
                updated_at TIMESTAMPTZ DEFAULT now()
            );
            CREATE TABLE IF NOT EXISTS reports (
                id TEXT PRIMARY KEY,
                doctor TEXT DEFAULT '',
                doctor_id INTEGER DEFAULT 0,
                patient_id INTEGER DEFAULT 0,
                patient_name TEXT DEFAULT '',
                patient_sex TEXT DEFAULT '',
                patient_age INTEGER DEFAULT 0,
                template TEXT DEFAULT '',
                raw_text TEXT DEFAULT '',
                structured JSONB DEFAULT '{}'::jsonb,
                edited JSONB DEFAULT '{}'::jsonb,
                audio_path TEXT DEFAULT '',
                voice_text TEXT DEFAULT '',
                template_id TEXT DEFAULT '',
                template_name TEXT DEFAULT '',
                description TEXT DEFAULT '',
                diagnosis TEXT DEFAULT '',
                audio_file TEXT DEFAULT '',
                asr_raw_text TEXT DEFAULT '',
                asr_corrected_text TEXT DEFAULT '',
                asr_source TEXT DEFAULT '',
                asr_quality REAL DEFAULT 0,
                intent_sites TEXT DEFAULT '',
                intent_findings TEXT DEFAULT '',
                intent_is_normal INTEGER DEFAULT 0,
                match_score REAL DEFAULT 0,
                matched_sites TEXT DEFAULT '',
                match_candidates TEXT DEFAULT '',
                variables JSONB DEFAULT '{}'::jsonb,
                status TEXT DEFAULT 'draft',
                created_at TIMESTAMPTZ DEFAULT now(),
                updated_at TIMESTAMPTZ DEFAULT now(),
                confirmed_at TIMESTAMPTZ,
                his_report_id TEXT DEFAULT '',
                external_ref TEXT DEFAULT ''
            );
            CREATE INDEX IF NOT EXISTS idx_reports_created ON reports(created_at);
            CREATE INDEX IF NOT EXISTS idx_reports_patient ON reports(patient_id);
            CREATE INDEX IF NOT EXISTS idx_reports_status ON reports(status);
            CREATE TABLE IF NOT EXISTS audit_log (
                id BIGSERIAL PRIMARY KEY,
                doctor TEXT DEFAULT 'system',
                action TEXT NOT NULL,
                target_type TEXT DEFAULT '',
                target_id TEXT DEFAULT '',
                detail TEXT DEFAULT '',
                ip_address TEXT DEFAULT '',
                patient_id INTEGER,
                input_text TEXT DEFAULT '',
                output_text TEXT DEFAULT '',
                operator TEXT DEFAULT 'system',
                created_at TIMESTAMPTZ DEFAULT now()
            );
            """
        )
        conn.commit()
