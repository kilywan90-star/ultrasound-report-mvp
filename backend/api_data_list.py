"""数据查询 API — 统一查询 reports + api_reports, 支持年月日过滤和自定义搜索"""

import re
from datetime import datetime
from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse
import db

router = APIRouter(prefix="/api/data", tags=["数据查询"])


@router.get("/list")
async def data_list(
    table: str = Query("all", description="表名: all|reports|api_reports|audit_log"),
    keyword: str = Query(None, description="全局搜索关键词 (匹配多字段)"),
    exam_type: str = Query(None, description="检查类型"),
    template_id: str = Query(None, description="模板ID"),
    date_from: str = Query(None, description="开始日期 YYYY-MM-DD"),
    date_to: str = Query(None, description="结束日期 YYYY-MM-DD"),
    year: int = Query(None, description="年份 (快捷)"),
    month: int = Query(None, ge=1, le=12, description="月份 (快捷)"),
    day: int = Query(None, ge=1, le=31, description="日 (快捷)"),
    limit: int = Query(100, ge=10, le=2000),
    offset: int = Query(0, ge=0),
):
    """
    统一数据查询接口。
    支持按年月日快速筛选, 也支持自定义 date_from/date_to 范围。
    所有字段可交叉组合查询。
    """
    # 日期处理
    if year and not date_from:
        date_from = f"{year}-01-01"
        date_to = f"{year}-12-31"
    if month and year:
        date_from = f"{year}-{month:02d}-01"
        # 简单月末计算
        next_month = month + 1 if month < 12 else 1
        next_year = year if month < 12 else year + 1
        date_to = f"{next_year}-{next_month:02d}-01"
    if day and year and month:
        date_from = f"{year}-{month:02d}-{day:02d}"
        date_to = f"{year}-{month:02d}-{day:02d}"

    results = []
    total = 0

    if table in ("all", "reports"):
        rows = db.report_search(
            keyword=keyword, exam_type=exam_type,
            template_id=template_id,
            date_from=date_from, date_to=date_to,
            limit=limit, offset=offset,
        )
        for r in rows:
            r["_table"] = "reports"
            # 提取关键字段
            structured = r.get("structured")
            if isinstance(structured, str):
                import json
                try: structured = json.loads(structured)
                except: structured = {}
            if isinstance(structured, dict):
                report = structured.get("report", structured)
                r["_study_see"] = report.get("study_see", "")[:200] if isinstance(report, dict) else ""
                r["_study_hint"] = report.get("study_hint", []) if isinstance(report, dict) else []
                r["_template_used"] = report.get("_template_matched", "") if isinstance(report, dict) else ""
                r["_method"] = report.get("_method", "") if isinstance(report, dict) else ""
            results.append(r)

    if table in ("all", "api_reports"):
        rows = db.api_report_search(
            keyword=keyword, date_from=date_from, date_to=date_to,
            limit=limit, offset=offset,
        )
        for r in rows:
            r["_table"] = "api_reports"
            r["_study_see"] = (r.get("DESCRIBES") or "")[:200]
            r["_study_hint"] = (r.get("DIAGNOSIS") or "")[:200]
            r["_template_used"] = r.get("ModuleName", "")
            r["_method"] = "pacs"
            results.append(r)

    if table in ("all", "audit_log"):
        rows = db.audit_log_search(
            keyword=keyword, action=None,
            limit=limit, offset=offset,
        )
        for r in rows:
            r["_table"] = "audit_log"
            r["_study_see"] = (r.get("output_text") or r.get("input_text") or "")[:200]
            r["_study_hint"] = ""
            r["_template_used"] = r.get("action", "")
            r["_method"] = "audit"
            results.append(r)

    # Sort by created_at desc
    results.sort(key=lambda x: str(x.get("created_at", "")), reverse=True)
    results = results[:limit]

    return JSONResponse({
        "success": True,
        "count": len(results),
        "filters": {
            "table": table, "keyword": keyword,
            "date_from": date_from, "date_to": date_to,
            "year": year, "month": month, "day": day,
        },
        "data": results,
    })
