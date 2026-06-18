"""
访问日志 API — 记录每个请求的 IP、地区、路径、耗时等

路由注册在 main.py 中:
    from routers.access_log import router as access_log_router
    app.include_router(access_log_router)

中间件也在 main.py 中，捕获请求后异步写入 SQLite。
"""
import logging
from fastapi import APIRouter, HTTPException, Query
from database import get_db

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/access-log", tags=["访问日志"])


def ensure_table():
    """确保 access_log 表存在（兼容旧版本）"""
    conn = get_db()
    try:
        conn.execute("""CREATE TABLE IF NOT EXISTS access_log (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            ip           TEXT DEFAULT '',
            ip_raw       TEXT DEFAULT '',
            province     TEXT DEFAULT '',
            city         TEXT DEFAULT '',
            path         TEXT NOT NULL DEFAULT '',
            method       TEXT DEFAULT 'GET',
            route_method TEXT DEFAULT '',
            template_used TEXT DEFAULT '',
            confidence   REAL DEFAULT 0,
            elapsed_ms   INTEGER DEFAULT 0,
            status_code  INTEGER DEFAULT 0,
            created_at   TEXT NOT NULL DEFAULT (datetime('now','localtime'))
        )""")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_access_log_created ON access_log(created_at)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_access_log_path ON access_log(path)")
        conn.commit()
    except Exception:
        pass
    finally:
        conn.close()


# 启动时确保表存在
ensure_table()


def write_log(ip_masked: str, ip_raw: str, province: str, city: str,
              path: str, method: str, status_code: int, elapsed_ms: int,
              route_method: str = "", template_used: str = "", confidence: float = 0):
    """写入一条访问日志（从中间件调用）"""
    try:
        conn = get_db()
        conn.execute(
            """INSERT INTO access_log (ip, ip_raw, province, city, path, method,
               status_code, elapsed_ms, route_method, template_used, confidence)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (ip_masked, ip_raw, province, city, path, method,
             status_code, elapsed_ms, route_method, template_used, confidence),
        )
        conn.commit()
    except Exception as e:
        logger.warning(f"访问日志写入失败: {e}")
    finally:
        try:
            conn.close()
        except Exception:
            pass


@router.get("")
def list_logs(
    limit: int = Query(100, ge=1, le=2000),
    offset: int = Query(0, ge=0),
    q: str = Query("", max_length=200),
    method_filter: str = Query("", max_length=50),
):
    """获取访问日志列表"""
    conn = get_db()
    params = []
    where = []

    if q:
        where.append("(ip LIKE ? OR province LIKE ? OR city LIKE ? OR path LIKE ? OR template_used LIKE ?)")
        kw = f"%{q}%"
        params.extend([kw, kw, kw, kw, kw])
    if method_filter:
        where.append("route_method = ?")
        params.append(method_filter)

    where_sql = " AND ".join(where) if where else "1=1"

    total = conn.execute(f"SELECT COUNT(*) AS n FROM access_log WHERE {where_sql}", params).fetchone()["n"]
    rows = conn.execute(
        f"SELECT id, ip, province, city, path, method, route_method, "
        f"template_used, confidence, elapsed_ms, status_code, created_at "
        f"FROM access_log WHERE {where_sql} ORDER BY id DESC LIMIT ? OFFSET ?",
        params + [limit, offset],
    ).fetchall()
    conn.close()

    return {
        "logs": [dict(r) for r in rows],
        "count": len(rows),
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get("/stats")
def get_stats():
    """获取概览统计"""
    conn = get_db()
    try:
        today = conn.execute(
            "SELECT COUNT(*) AS n, SUM(CASE WHEN status_code>=400 THEN 1 ELSE 0 END) AS errs "
            "FROM access_log WHERE date(created_at)=date('now','localtime')"
        ).fetchone()
        all_time = conn.execute("SELECT COUNT(*) AS n FROM access_log").fetchone()
        total_today = today["n"] if today else 0
        errs_today = today["errs"] if today and today["errs"] else 0
        total_all = all_time["n"] if all_time else 0

        # 方法分布
        method_rows = conn.execute(
            "SELECT route_method, COUNT(*) AS n FROM access_log "
            "WHERE route_method!='' GROUP BY route_method ORDER BY n DESC"
        ).fetchall()
        method_dist = [{"method": r["route_method"], "count": r["n"]} for r in method_rows]

        # 地区分布 (Top10)
        region_rows = conn.execute(
            "SELECT province, city, COUNT(*) AS n FROM access_log "
            "WHERE province!='' GROUP BY province, city ORDER BY n DESC LIMIT 10"
        ).fetchall()
        region_dist = [{"province": r["province"], "city": r["city"], "count": r["n"]} for r in region_rows]

        return {
            "today": total_today,
            "errors_today": errs_today,
            "total": total_all,
            "method_distribution": method_dist,
            "region_distribution": region_dist,
        }
    finally:
        conn.close()


@router.delete("/{log_id}")
def delete_log(log_id: int):
    """删除单条日志"""
    conn = get_db()
    try:
        cur = conn.execute("DELETE FROM access_log WHERE id=?", (log_id,))
        conn.commit()
        if cur.rowcount == 0:
            raise HTTPException(404, "日志不存在")
        return {"status": "ok"}
    finally:
        conn.close()
