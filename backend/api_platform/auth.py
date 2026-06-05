"""API Platform — API Key 鉴权"""

import uuid
import hashlib
import secrets
from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse

from .db import tenant_get_by_key


def generate_api_key() -> str:
    return f"sk-{uuid.uuid4().hex}"


def generate_api_secret() -> str:
    return secrets.token_hex(32)


def verify_api_key(api_key: str) -> dict | None:
    """验证 API Key, 返回 tenant 字典或 None"""
    if not api_key:
        return None
    # Accept both "Bearer sk-xxx" and bare "sk-xxx"
    if api_key.startswith("Bearer "):
        api_key = api_key[7:]
    return tenant_get_by_key(api_key.strip())


# ── FastAPI dependencies / middleware ──

class ApiKeyAuth:
    """FastAPI 依赖注入: 从 Authorization header 提取并验证 API Key"""

    async def __call__(self, request: Request) -> dict:
        auth = request.headers.get("Authorization", "")
        if not auth:
            raise HTTPException(status_code=401, detail="缺少 API Key — 请在 Authorization header 中提供 Bearer <api_key>")

        tenant = verify_api_key(auth)
        if not tenant:
            raise HTTPException(status_code=403, detail="API Key 无效或已被禁用")

        return tenant


# 使用示例:
#   from api_platform.auth import ApiKeyAuth
#   require_auth = ApiKeyAuth()
#
#   @app.post("/v1/structure")
#   async def structure(req: StructureRequest, tenant=Depends(require_auth)):
#       ...
