"""API Platform — 多租户数据库模块"""

import sqlite3
import threading
from pathlib import Path
from datetime import datetime

DB_PATH = Path(__file__).resolve().parent.parent / "api_platform.db"

_local = threading.local()

def _conn() -> sqlite3.Connection:
    if not hasattr(_local, "conn") or _local.conn is None:
        _local.conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
        _local.conn.row_factory = sqlite3.Row
        _local.conn.execute("PRAGMA journal_mode=WAL")
        _local.conn.execute("PRAGMA foreign_keys=ON")
    return _local.conn


def init_db():
    c = _conn()
    c.executescript("""
        CREATE TABLE IF NOT EXISTS api_tenants (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT NOT NULL,
            contact     TEXT,
            email       TEXT UNIQUE,
            plan        TEXT NOT NULL DEFAULT 'free'
                        CHECK(plan IN ('free','basic','pro')),
            api_key     TEXT UNIQUE NOT NULL,
            is_active   INTEGER NOT NULL DEFAULT 1,
            created_at  TEXT NOT NULL DEFAULT (datetime('now','localtime')),
            updated_at  TEXT NOT NULL DEFAULT (datetime('now','localtime'))
        );

        -- 注册日志 (每次 signup 记录)
        CREATE TABLE IF NOT EXISTS api_registrations (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            tenant_id   INTEGER NOT NULL REFERENCES api_tenants(id),
            name        TEXT NOT NULL,
            email       TEXT NOT NULL,
            contact     TEXT,
            ip_address  TEXT,
            user_agent  TEXT,
            created_at  TEXT NOT NULL DEFAULT (datetime('now','localtime'))
        );

        -- 订单记录 (每次购买/升级套餐)
        CREATE TABLE IF NOT EXISTS api_orders (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            tenant_id   INTEGER NOT NULL REFERENCES api_tenants(id),
            plan_before TEXT,
            plan_after  TEXT NOT NULL,
            amount      REAL DEFAULT 0,
            status      TEXT NOT NULL DEFAULT 'completed'
                        CHECK(status IN ('pending','completed','refunded','cancelled')),
            note        TEXT,
            created_at  TEXT NOT NULL DEFAULT (datetime('now','localtime'))
        );

        -- 音频文件索引 (每次 transcribe 上传)
        CREATE TABLE IF NOT EXISTS audio_files (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            tenant_id   INTEGER NOT NULL REFERENCES api_tenants(id),
            patient_id  TEXT NOT NULL,
            file_path   TEXT NOT NULL,
            file_name   TEXT NOT NULL,
            file_size   INTEGER NOT NULL,
            audio_duration REAL DEFAULT 0,
            asr_text    TEXT,
            report_id   TEXT,
            created_at  TEXT NOT NULL DEFAULT (datetime('now','localtime'))
        );

        CREATE TABLE IF NOT EXISTS api_usage (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            tenant_id   INTEGER NOT NULL REFERENCES api_tenants(id),
            endpoint    TEXT NOT NULL,
            tokens_in   INTEGER DEFAULT 0,
            tokens_out  INTEGER DEFAULT 0,
            asr_seconds REAL DEFAULT 0,
            cost        REAL DEFAULT 0,
            billed      REAL DEFAULT 0,
            created_at  TEXT NOT NULL DEFAULT (datetime('now','localtime'))
        );

        CREATE TABLE IF NOT EXISTS api_rate_limits (
            tenant_id   INTEGER NOT NULL REFERENCES api_tenants(id),
            endpoint    TEXT NOT NULL DEFAULT '*',
            rpm         INTEGER DEFAULT 10,
            rpd         INTEGER DEFAULT 500,
            PRIMARY KEY (tenant_id, endpoint)
        );

        CREATE INDEX IF NOT EXISTS idx_api_usage_tenant ON api_usage(tenant_id, created_at);
        CREATE INDEX IF NOT EXISTS idx_api_usage_endpoint ON api_usage(endpoint, created_at);
        CREATE INDEX IF NOT EXISTS idx_registrations_tenant ON api_registrations(tenant_id);
        CREATE INDEX IF NOT EXISTS idx_registrations_date ON api_registrations(created_at);
        CREATE INDEX IF NOT EXISTS idx_orders_tenant ON api_orders(tenant_id);
        CREATE INDEX IF NOT EXISTS idx_orders_date ON api_orders(created_at);
        CREATE INDEX IF NOT EXISTS idx_audio_tenant ON audio_files(tenant_id, created_at);
        CREATE INDEX IF NOT EXISTS idx_audio_patient ON audio_files(patient_id);
        CREATE INDEX IF NOT EXISTS idx_audio_date ON audio_files(created_at);
    """)
    c.commit()


# ── Tenant CRUD ──

def tenant_create(name: str, plan: str = "free", email: str = None,
                  contact: str = None, api_key: str = None) -> dict:
    c = _conn()
    cur = c.execute(
        """INSERT INTO api_tenants (name, plan, email, contact, api_key)
           VALUES (?,?,?,?,?)""",
        (name, plan, email, contact, api_key),
    )
    # 创建对应限流记录
    c.execute(
        "INSERT OR IGNORE INTO api_rate_limits (tenant_id, endpoint) VALUES (?, '*')",
        (cur.lastrowid,),
    )
    c.commit()
    return tenant_get(cur.lastrowid)


def tenant_get(tenant_id: int) -> dict | None:
    c = _conn()
    row = c.execute("SELECT * FROM api_tenants WHERE id=?", (tenant_id,)).fetchone()
    return dict(row) if row else None


def tenant_get_by_key(api_key: str) -> dict | None:
    c = _conn()
    row = c.execute(
        "SELECT * FROM api_tenants WHERE api_key=? AND is_active=1", (api_key,)
    ).fetchone()
    return dict(row) if row else None


def tenant_get_by_email(email: str) -> dict | None:
    c = _conn()
    row = c.execute(
        "SELECT * FROM api_tenants WHERE email=? AND is_active=1", (email,)
    ).fetchone()
    return dict(row) if row else None


def tenant_list(include_inactive: bool = False) -> list[dict]:
    c = _conn()
    if include_inactive:
        rows = c.execute("SELECT * FROM api_tenants ORDER BY created_at DESC").fetchall()
    else:
        rows = c.execute(
            "SELECT * FROM api_tenants WHERE is_active=1 ORDER BY created_at DESC"
        ).fetchall()
    return [dict(r) for r in rows]


def tenant_update(tenant_id: int, **kwargs) -> dict | None:
    allowed = {"name", "contact", "email", "plan", "is_active"}
    fields = {k: v for k, v in kwargs.items() if k in allowed}
    if not fields:
        return tenant_get(tenant_id)
    fields["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    c = _conn()
    sets = ", ".join(f"{k}=?" for k in fields)
    vals = list(fields.values()) + [tenant_id]
    c.execute(f"UPDATE api_tenants SET {sets} WHERE id=?", vals)
    c.commit()
    return tenant_get(tenant_id)


# ── Usage ──

def usage_record(tenant_id: int, endpoint: str, tokens_in: int = 0,
                 tokens_out: int = 0, asr_seconds: float = 0.0,
                 cost: float = 0.0, billed: float = 0.0) -> int:
    c = _conn()
    cur = c.execute(
        """INSERT INTO api_usage (tenant_id, endpoint, tokens_in, tokens_out,
           asr_seconds, cost, billed) VALUES (?,?,?,?,?,?,?)""",
        (tenant_id, endpoint, tokens_in, tokens_out, asr_seconds, cost, billed),
    )
    c.commit()
    return cur.lastrowid


def usage_get_monthly(tenant_id: int, year: int = None, month: int = None) -> dict:
    """返回本月调用统计"""
    now = datetime.now()
    year = year or now.year
    month = month or now.month
    period = f"{year}-{month:02d}"
    c = _conn()
    row = c.execute(
        """SELECT COUNT(*) as total_calls,
                  SUM(tokens_in) as total_tokens_in,
                  SUM(tokens_out) as total_tokens_out,
                  SUM(asr_seconds) as total_asr_seconds,
                  SUM(cost) as total_cost,
                  SUM(billed) as total_billed
           FROM api_usage
           WHERE tenant_id=? AND created_at LIKE ?""",
        (tenant_id, f"{period}%"),
    ).fetchone()
    d = dict(row)
    for k in d:
        d[k] = d[k] or 0
    d["period"] = period
    return d


def usage_get_all_monthly(year: int = None, month: int = None) -> list[dict]:
    """所有租户本月用量汇总"""
    now = datetime.now()
    year = year or now.year
    month = month or now.month
    period = f"{year}-{month:02d}"
    c = _conn()
    rows = c.execute(
        """SELECT t.id, t.name, t.plan,
                  COUNT(u.id) as total_calls,
                  COALESCE(SUM(u.tokens_in),0) as total_tokens_in,
                  COALESCE(SUM(u.tokens_out),0) as total_tokens_out,
                  COALESCE(SUM(u.asr_seconds),0) as total_asr_seconds,
                  COALESCE(SUM(u.cost),0) as total_cost,
                  COALESCE(SUM(u.billed),0) as total_billed
           FROM api_tenants t
           LEFT JOIN api_usage u ON t.id=u.tenant_id AND u.created_at LIKE ?
           GROUP BY t.id ORDER BY total_billed DESC""",
        (f"{period}%",),
    ).fetchall()
    return [dict(r) for r in rows]


# ── Rate Limit Config ──

def rate_limit_get(tenant_id: int, endpoint: str = "*") -> dict:
    c = _conn()
    row = c.execute(
        "SELECT * FROM api_rate_limits WHERE tenant_id=? AND endpoint=?",
        (tenant_id, endpoint),
    ).fetchone()
    if row:
        return dict(row)
    # fallback to wildcard
    row = c.execute(
        "SELECT * FROM api_rate_limits WHERE tenant_id=? AND endpoint='*'",
        (tenant_id,),
    ).fetchone()
    return dict(row) if row else {"rpm": 10, "rpd": 500}


def rate_limit_set(tenant_id: int, endpoint: str = "*", rpm: int = 10, rpd: int = 500):
    c = _conn()
    c.execute(
        """INSERT OR REPLACE INTO api_rate_limits (tenant_id, endpoint, rpm, rpd)
           VALUES (?,?,?,?)""",
        (tenant_id, endpoint, rpm, rpd),
    )
    c.commit()


# ── Registration Log ──

def registration_log(tenant_id: int, name: str, email: str,
                     contact: str = None, ip: str = None, ua: str = None) -> int:
    c = _conn()
    cur = c.execute(
        """INSERT INTO api_registrations (tenant_id, name, email, contact, ip_address, user_agent)
           VALUES (?,?,?,?,?,?)""",
        (tenant_id, name, email, contact, ip, ua),
    )
    c.commit()
    return cur.lastrowid


def registration_list(days: int = 30) -> list[dict]:
    c = _conn()
    rows = c.execute(
        """SELECT r.*, t.name as tenant_name, t.plan
           FROM api_registrations r JOIN api_tenants t ON r.tenant_id=t.id
           WHERE r.created_at >= datetime('now','localtime','-'||?||' days')
           ORDER BY r.created_at DESC""",
        (days,),
    ).fetchall()
    return [dict(r) for r in rows]


# ── Order Log ──

def order_log(tenant_id: int, plan_before: str, plan_after: str,
              amount: float = 0, status: str = "completed", note: str = None) -> int:
    c = _conn()
    cur = c.execute(
        """INSERT INTO api_orders (tenant_id, plan_before, plan_after, amount, status, note)
           VALUES (?,?,?,?,?,?)""",
        (tenant_id, plan_before, plan_after, amount, status, note),
    )
    c.commit()
    return cur.lastrowid


def order_list(days: int = 90) -> list[dict]:
    c = _conn()
    rows = c.execute(
        """SELECT o.*, t.name as tenant_name
           FROM api_orders o JOIN api_tenants t ON o.tenant_id=t.id
           WHERE o.created_at >= datetime('now','localtime','-'||?||' days')
           ORDER BY o.created_at DESC""",
        (days,),
    ).fetchall()
    return [dict(r) for r in rows]


def order_total_revenue(days: int = 30) -> float:
    c = _conn()
    row = c.execute(
        """SELECT COALESCE(SUM(amount),0) as total
           FROM api_orders
           WHERE status='completed'
           AND created_at >= datetime('now','localtime','-'||?||' days')""",
        (days,),
    ).fetchone()
    return row[0] if row else 0.0


# ── Audio File Index ──

def audio_file_log(tenant_id: int, patient_id: str, file_path: str,
                   file_name: str, file_size: int, audio_duration: float = 0,
                   asr_text: str = None, report_id: str = None) -> int:
    c = _conn()
    cur = c.execute(
        """INSERT INTO audio_files (tenant_id, patient_id, file_path, file_name,
           file_size, audio_duration, asr_text, report_id)
           VALUES (?,?,?,?,?,?,?,?)""",
        (tenant_id, patient_id, file_path, file_name, file_size,
         audio_duration, asr_text[:500] if asr_text else None, report_id),
    )
    c.commit()
    return cur.lastrowid


def audio_file_list(tenant_id: int = None, days: int = 30, limit: int = 100) -> list[dict]:
    c = _conn()
    if tenant_id:
        rows = c.execute(
            """SELECT a.*, t.name as tenant_name
               FROM audio_files a JOIN api_tenants t ON a.tenant_id=t.id
               WHERE a.tenant_id=? AND a.created_at >= datetime('now','localtime','-'||?||' days')
               ORDER BY a.created_at DESC LIMIT ?""",
            (tenant_id, days, limit),
        ).fetchall()
    else:
        rows = c.execute(
            """SELECT a.*, t.name as tenant_name
               FROM audio_files a JOIN api_tenants t ON a.tenant_id=t.id
               WHERE a.created_at >= datetime('now','localtime','-'||?||' days')
               ORDER BY a.created_at DESC LIMIT ?""",
            (days, limit),
        ).fetchall()
    return [dict(r) for r in rows]


def audio_file_stats() -> dict:
    c = _conn()
    row = c.execute(
        """SELECT COUNT(*) as total_files,
                  COALESCE(SUM(file_size),0) as total_bytes,
                  COUNT(DISTINCT tenant_id) as tenant_count
           FROM audio_files"""
    ).fetchone()
    return dict(row) if row else {"total_files": 0, "total_bytes": 0, "tenant_count": 0}


# 启动时建表
init_db()
