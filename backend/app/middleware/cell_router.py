"""Cell-aware routing middleware — redirects requests to the correct regional cell."""

from __future__ import annotations

import json
import logging
from typing import Dict, Optional

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import RedirectResponse, Response

from app.config import settings

logger = logging.getLogger(__name__)

_SKIP_PATHS = frozenset({"/health", "/metrics", "/docs", "/openapi.json", "/redoc"})

_cell_url_cache: Optional[Dict[str, str]] = None


def _reset_cell_url_cache() -> None:
    global _cell_url_cache
    _cell_url_cache = None


def _parse_cell_urls() -> Dict[str, str]:
    global _cell_url_cache
    if _cell_url_cache is not None:
        return _cell_url_cache
    raw = settings.cell_urls
    if not raw:
        _cell_url_cache = {}
        return _cell_url_cache
    try:
        parsed = json.loads(raw)
        if not isinstance(parsed, dict):
            logger.error("CELL_URLS must be a JSON object, got %s", type(parsed).__name__)
            _cell_url_cache = {}
            return _cell_url_cache
        _cell_url_cache = {str(k): str(v) for k, v in parsed.items()}
        return _cell_url_cache
    except json.JSONDecodeError as exc:
        logger.error("Failed to parse CELL_URLS: %s", exc)
        _cell_url_cache = {}
        return _cell_url_cache


async def _resolve_tenant_region(request: Request) -> Optional[str]:
    """Resolve the tenant's data_region from JWT or API key."""
    try:
        from app.services.auth.jwt_service import decode_token
        from sqlalchemy import select
        from app.models.user import User
        from app.models.tenant import Tenant
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
                            t_result = await db.execute(
                                select(Tenant).filter(Tenant.tenant_id == user.tenant_id)
                            )
                            tenant = t_result.scalars().first()
                            if tenant:
                                return tenant.data_region
    except Exception:
        pass

    # API key path
    api_key = request.headers.get("X-API-Key")
    if api_key:
        try:
            import hashlib
            from sqlalchemy import select
            from app.models.intel import Bank
            from app.models.tenant import Tenant
            from app.database import AsyncSessionLocal

            api_key_hash = hashlib.sha256(api_key.encode()).hexdigest()
            async with AsyncSessionLocal() as db:
                result = await db.execute(
                    select(Bank).filter(Bank.api_key_hash == api_key_hash)
                )
                bank = result.scalars().first()
                if bank and bank.tenant_id:
                    t_result = await db.execute(
                        select(Tenant).filter(Tenant.tenant_id == bank.tenant_id)
                    )
                    tenant = t_result.scalars().first()
                    if tenant:
                        return tenant.data_region
        except Exception:
            pass

    return None


class CellRoutingMiddleware(BaseHTTPMiddleware):
    """Route requests to the correct regional cell based on tenant's data_region.

    Single-cell mode (cell_routing_enabled=False): all requests pass through.
    Multi-cell mode: if tenant's region differs from this cell, return a 3xx
    redirect to the correct cell URL. The redirect carries no PII.
    """

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        if not settings.cell_routing_enabled:
            return await call_next(request)

        path = request.url.path
        if path in _SKIP_PATHS or path.startswith("/embed"):
            return await call_next(request)

        tenant_region = await _resolve_tenant_region(request)

        if tenant_region is None or tenant_region == settings.cell_region:
            return await call_next(request)

        cell_urls = _parse_cell_urls()
        target_url = cell_urls.get(tenant_region)
        if not target_url:
            logger.warning(
                "No cell URL configured for region %s — allowing request to proceed",
                tenant_region,
            )
            return await call_next(request)

        redirect_url = f"{target_url.rstrip('/')}{request.url.path}"

        logger.info(
            "Cell routing redirect: tenant_region=%s (this cell=%s) -> %s",
            tenant_region,
            settings.cell_region,
            target_url,
        )
        return RedirectResponse(url=redirect_url, status_code=307)
