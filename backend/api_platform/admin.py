"""API Platform — 管理后台路由"""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from .db import (
    tenant_create, tenant_get, tenant_list, tenant_update,
    usage_get_monthly, usage_get_all_monthly,
    rate_limit_get, rate_limit_set,
    tenant_get_by_key,
    registration_list, order_list, order_total_revenue,
    audio_file_list, audio_file_stats,
    order_log,
    trace_log_list,
    error_report_create, error_report_list,
)
from .auth import generate_api_key
from .billing import PLANS, get_plan

router = APIRouter(prefix="/api/admin", tags=["管理后台"])


# ── Request models ──

class TenantCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    plan: str = Field(default="free")
    email: str | None = None
    contact: str | None = None


class TenantUpdateRequest(BaseModel):
    name: str | None = None
    plan: str | None = None
    email: str | None = None
    contact: str | None = None
    is_active: int | None = None


# ── Tenant CRUD ──

@router.get("/tenants")
async def list_tenants(include_inactive: bool = False):
    tenants = tenant_list(include_inactive)
    # Add monthly usage to each
    for t in tenants:
        t["monthly_usage"] = usage_get_monthly(t["id"])
    return {"success": True, "tenants": tenants}


@router.post("/tenants")
async def create_tenant(req: TenantCreateRequest):
    if req.plan not in PLANS:
        raise HTTPException(400, f"无效套餐: {req.plan}, 可选: {list(PLANS.keys())}")
    api_key = generate_api_key()
    tenant = tenant_create(
        name=req.name, plan=req.plan,
        email=req.email, contact=req.contact,
        api_key=api_key,
    )
    return {"success": True, "tenant": tenant, "api_key": api_key}


@router.get("/tenants/{tenant_id}")
async def get_tenant(tenant_id: int):
    t = tenant_get(tenant_id)
    if not t:
        raise HTTPException(404, "租户不存在")
    t["monthly_usage"] = usage_get_monthly(tenant_id)
    t["plan_info"] = get_plan(t["plan"])
    return {"success": True, "tenant": t}


@router.put("/tenants/{tenant_id}")
async def update_tenant(tenant_id: int, req: TenantUpdateRequest):
    t = tenant_get(tenant_id)
    if not t:
        raise HTTPException(404, "租户不存在")
    updates = {k: v for k, v in req.model_dump().items() if v is not None}
    if "plan" in updates and updates["plan"] not in PLANS:
        raise HTTPException(400, f"无效套餐: {updates['plan']}")
    result = tenant_update(tenant_id, **updates)
    return {"success": True, "tenant": result}


# ── Usage dashboard ──

@router.get("/usage")
async def all_usage(year: int = None, month: int = None):
    rows = usage_get_all_monthly(year, month)
    summary = {
        "total_tenants": len(rows),
        "total_calls": sum(r["total_calls"] for r in rows),
        "total_billed": round(sum(r["total_billed"] for r in rows), 2),
        "total_cost": round(sum(r["total_cost"] for r in rows), 4),
    }
    return {"success": True, "summary": summary, "tenants": rows}


@router.get("/usage/{tenant_id}")
async def tenant_usage(tenant_id: int, year: int = None, month: int = None):
    t = tenant_get(tenant_id)
    if not t:
        raise HTTPException(404, "租户不存在")
    monthly = usage_get_monthly(tenant_id, year, month)
    plan = get_plan(t["plan"])
    return {
        "success": True,
        "tenant": {"id": t["id"], "name": t["name"], "plan": t["plan"]},
        "usage": monthly,
        "plan": {
            "name": plan["name"],
            "monthly_quota": plan["monthly_quota"],
            "remaining": max(0, plan["monthly_quota"] - monthly["total_calls"]),
            "overage_price": plan["overage_price"],
        },
    }


# ── Plans ──

@router.get("/plans")
async def list_plans():
    return {"success": True, "plans": PLANS}


# ── Rate limits ──

@router.get("/tenants/{tenant_id}/ratelimit")
async def get_ratelimit(tenant_id: int, endpoint: str = "*"):
    t = tenant_get(tenant_id)
    if not t:
        raise HTTPException(404, "租户不存在")
    rl = rate_limit_get(tenant_id, endpoint)
    return {"success": True, "rate_limit": rl}


class RateLimitSetRequest(BaseModel):
    endpoint: str = "*"
    rpm: int = 10
    rpd: int = 500


@router.put("/tenants/{tenant_id}/ratelimit")
async def set_ratelimit(tenant_id: int, req: RateLimitSetRequest):
    t = tenant_get(tenant_id)
    if not t:
        raise HTTPException(404, "租户不存在")
    rate_limit_set(tenant_id, req.endpoint, req.rpm, req.rpd)
    return {"success": True, "message": f"限流已更新: {req.endpoint} RPM={req.rpm} RPD={req.rpd}"}


# ── 自助升级 (用户通过自己的 API Key 升级套餐) ──

class UpgradeRequest(BaseModel):
    api_key: str = Field(..., min_length=10, description="用户的 API Key")
    plan: str = Field(..., description="目标套餐: basic / pro")


@router.post("/upgrade-by-key")
async def upgrade_by_key(req: UpgradeRequest):
    """用户自助升级套餐 — 通过 API Key 验证身份后直接升级"""
    if req.plan not in PLANS:
        raise HTTPException(400, f"无效套餐: {req.plan}, 可选: {list(PLANS.keys())}")
    t = tenant_get_by_key(req.api_key)
    if not t:
        raise HTTPException(404, "API Key 无效或已禁用")
    if t["plan"] == req.plan:
        return {
            "success": True,
            "msg": f"当前已是 {PLANS[req.plan]['name']}, 无需重复升级",
            "plan": t["plan"],
            "plan_name": PLANS[req.plan]["name"],
            "monthly_quota": PLANS[req.plan]["monthly_quota"],
        }

    plan_before = t["plan"]
    result = tenant_update(t["id"], plan=req.plan)

    # 记录订单
    plan_info_target = PLANS[req.plan]
    amount = plan_info_target.get("monthly_fee", 0)
    try:
        order_log(
            tenant_id=t["id"], plan_before=plan_before, plan_after=req.plan,
            amount=amount, status="completed",
            note=f"自助升级: {plan_before} → {req.plan}",
        )
    except Exception as e:
        import logging
        logging.warning(f"order_log failed: {e}")

    plan_info = PLANS[req.plan]
    return {
        "success": True,
        "msg": f"升级成功: {plan_before} → {req.plan}",
        "plan": req.plan,
        "plan_name": plan_info["name"],
        "monthly_quota": plan_info["monthly_quota"],
        "monthly_fee": plan_info["monthly_fee"],
        "overage_price": plan_info["overage_price"],
    }


# ── Registration Log ──

@router.get("/registrations")
async def list_registrations(days: int = 30):
    rows = registration_list(days)
    return {"success": True, "total": len(rows), "registrations": rows}


# ── Order Log ──

@router.get("/orders")
async def list_orders(days: int = 90):
    rows = order_list(days)
    revenue = order_total_revenue(days)
    return {"success": True, "total": len(rows), "revenue": round(revenue, 2), "orders": rows}


# ── Audio File Index ──

@router.get("/audio-files")
async def list_audio_files(tenant_id: int = None, days: int = 30, limit: int = 100):
    rows = audio_file_list(tenant_id=tenant_id, days=days, limit=limit)
    stats = audio_file_stats()
    return {"success": True, "total": len(rows), "stats": stats, "files": rows}


# ── Trace Log Query ──

@router.get("/trace-logs")
async def list_trace_logs(days: int = 7, limit: int = 100,
                           patient_id: str = None, date: str = None,
                           status: str = None):
    logs = trace_log_list(days=days, limit=limit, patient_id=patient_id,
                          date=date, status=status)
    return {"success": True, "total": len(logs), "logs": logs}


# ── Error Reports ──

class ErrorReportRequest(BaseModel):
    request_id: str | None = None
    raw_input: str = Field(..., min_length=1, max_length=5000)
    ai_output: str = Field(..., min_length=1, max_length=5000)
    expected_output: str = Field(..., min_length=1, max_length=5000)
    error_type: str = Field(..., min_length=1, max_length=50)
    severity: str = Field(default="moderate")
    description: str = Field(default="", max_length=2000)
    reproducible: str = Field(default="yes")


@router.post("/error-reports")
async def create_error_report(req: ErrorReportRequest):
    rid = error_report_create(req.model_dump())
    return {"success": True, "id": rid, "msg": "错误反馈已提交"}


@router.get("/error-reports")
async def list_error_reports(limit: int = 50):
    reports = error_report_list(limit=limit)
    return {"success": True, "total": len(reports), "reports": reports}
