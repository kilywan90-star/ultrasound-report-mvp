"""API Platform — 管理后台路由"""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from .db import (
    tenant_create, tenant_get, tenant_list, tenant_update,
    usage_get_monthly, usage_get_all_monthly,
    rate_limit_get, rate_limit_set,
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
