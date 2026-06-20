"""Tenant context middleware — resolves tenant from JWT or API key."""

from __future__ import annotations

import logging
from contextlib import contextmanager
from contextvars import ContextVar

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger(__name__)

tenant_context: ContextVar[str | None] = ContextVar("tenant_id", default=None)


class TenantContextMiddleware(BaseHTTPMiddleware):
    """Resolve tenant_id from JWT sub or X-API-Key and set tenant_context."""

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        token = tenant_context.set(None)
        try:
            tenant_id = await _resolve_tenant(request)
            if tenant_id:
                token = tenant_context.set(tenant_id)
                request.state.tenant_id = tenant_id
            response: Response = await call_next(request)
        finally:
            tenant_context.reset(token)
        return response


async def _resolve_tenant(request: Request) -> str | None:
    """Try JWT sub -> User.tenant_id, then X-API-Key -> Bank.tenant_id, then X-Tenant-Id header."""
    # 0. X-Tenant-Id header (lowest priority — can be overridden by JWT/API key)
    tenant_header = request.headers.get("X-Tenant-Id")
    if tenant_header:
        return tenant_header

    # 1. JWT path: extract user from token, look up tenant_id
    try:
        from app.services.auth.jwt_service import decode_token
        from sqlalchemy import select
        from app.models.user import User
        from app.database import AsyncSessionLocal

        cookie_token = request.cookies.get("ts_access_token")
        auth_header = request.headers.get("authorization", "")
        token = cookie_token or (
            auth_header.replace("Bearer ", "") if auth_header.startswith("Bearer ") else None
        )
        if token:
            payload = decode_token(token)
            if payload and payload.get("type") == "access":
                user_id = payload.get("sub")
                if user_id:
                    async with AsyncSessionLocal() as db:
                        result = await db.execute(select(User).filter(User.id == int(user_id)))
                        user = result.scalars().first()
                        if user and user.tenant_id:
                            return user.tenant_id
    except Exception:
        pass

    # 2. API key path: X-API-Key -> Bank.api_key_hash -> Bank.tenant_id
    api_key = request.headers.get("X-API-Key")
    if api_key:
        try:
            import hashlib
            from sqlalchemy import select
            from app.models.intel import Bank
            from app.database import AsyncSessionLocal

            api_key_hash = hashlib.sha256(api_key.encode()).hexdigest()
            async with AsyncSessionLocal() as db:
                result = await db.execute(select(Bank).filter(Bank.api_key_hash == api_key_hash))
                bank = result.scalars().first()
                if bank and bank.tenant_id:
                    return bank.tenant_id
        except Exception:
            pass

    return None


def get_current_tenant() -> str | None:
    """Return the current tenant_id from context, or None if unset."""
    return tenant_context.get()


@contextmanager
def bypass_tenant():
    """Temporarily set tenant_context to None (super_admin only, logs the bypass)."""
    logger.warning(
        "TENANT_BYPASS activated — cross-tenant access allowed. "
        "Ensure caller is super_admin."
    )
    token = tenant_context.set(None)
    try:
        yield
    finally:
        tenant_context.reset(token)
