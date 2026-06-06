"""系统日志 API — 前端日志面板数据源"""

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse
import db

router = APIRouter(prefix="/api/system", tags=["系统日志"])


@router.get("/log")
async def system_log(
    q: str = Query(None, description="搜索关键词"),
    level: str = Query(None, description="日志级别: error|warn|info"),
    limit: int = Query(500, ge=10, le=2000),
    offset: int = Query(0, ge=0),
):
    """读取 audit_log 和 trace_logs, 支持搜索和过滤"""
    logs = db.audit_log_search(
        keyword=q,
        action=level,
        limit=limit,
        offset=offset,
    )
    return JSONResponse({
        "success": True,
        "count": len(logs),
        "logs": logs,
        "filters": {"q": q, "level": level},
    })
