"""Billing quota enforcement dependency.

Usage: Depends(require_billing_quota("analyze"))
"""

import asyncio
import logging
from typing import Optional

from fastapi import Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_async_db

logger = logging.getLogger(__name__)


def require_billing_quota(endpoint: str):
    """Factory that returns a dependency checking quota for the given endpoint."""

    async def _check(
        request: Request,
        db: AsyncSession = Depends(get_async_db),
    ) -> None:
        from app.config import settings
        if not settings.billing_enabled:
            return

        bank_id = None
        user_id = None

        # Try bank auth (X-API-Key header)
        from app.models.intel import Bank
        from sqlalchemy import select
        api_key = request.headers.get("X-API-Key")
        if api_key:
            import hashlib
            key_hash = hashlib.sha256(api_key.encode()).hexdigest()
            result = await db.execute(
                select(Bank).filter(Bank.api_key_hash == key_hash)
            )
            bank = result.scalars().first()
            if bank:
                bank_id = bank.bank_id

        # Try JWT auth
        if not bank_id:
            token = request.cookies.get("ts_access_token")
            if not token:
                auth_header = request.headers.get("Authorization", "")
                if auth_header.startswith("Bearer "):
                    token = auth_header[7:]
            if token:
                from app.services.auth.jwt_service import decode_token
                payload = decode_token(token)
                if payload and payload.get("sub"):
                    user_id = int(payload["sub"])

        if not bank_id and not user_id:
            return

        from app.services.billing.usage_service import check_quota
        allowed, quota_info = await check_quota(
            db, bank_id=bank_id, user_id=user_id, endpoint=endpoint
        )

        if not allowed:
            raise HTTPException(
                status_code=429,
                detail={
                    "error": "QuotaExceeded",
                    "message": (
                        f"Monthly {endpoint} limit reached "
                        f"({quota_info['used']}/{quota_info['limit']})"
                    ),
                    "quota": quota_info,
                },
                headers={
                    "Retry-After": "3600",
                    "X-Tier-Upgrade-URL": "/api/v1/billing/portal",
                },
            )

        # Fire-and-forget usage recording — peek at body without consuming the stream.
        # request.body() caches the bytes internally so downstream handlers can
        # still call request.json() without issues.
        session_id = None
        try:
            body_bytes = await request.body()
            if body_bytes:
                import json as _json

                body = _json.loads(body_bytes)
                session_id = body.get("session_metadata", {}).get("session_id")
        except Exception:
            pass

        asyncio.create_task(
            _record_usage_safe(bank_id, user_id, endpoint, session_id)
        )

    return _check


async def _record_usage_safe(
    bank_id: Optional[str],
    user_id: Optional[int],
    endpoint: str,
    session_id: Optional[str],
) -> None:
    """Record usage in a separate session."""
    try:
        from app.database import AsyncSessionLocal
        from app.services.billing.usage_service import record_usage
        async with AsyncSessionLocal() as db:
            await record_usage(
                db,
                bank_id=bank_id,
                user_id=user_id,
                endpoint=endpoint,
                session_id=session_id,
            )
            await db.commit()
    except Exception as exc:
        logger.warning("Usage recording failed: %s", exc)
