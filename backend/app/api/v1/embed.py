"""Embeddable Trust Console API — issues scoped JWT tokens for iframe embedding."""

import logging
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import verify_api_key
from app.database import get_async_db
from app.models.tenant import Tenant
from app.services.auth.jwt_service import create_access_token

logger = logging.getLogger(__name__)

router = APIRouter()

EMBED_PERMISSIONS = ["SCAN_READ", "REPORT_CREATE", "INTEL_READ"]
EMBED_TOKEN_EXPIRY = timedelta(hours=1)

ADMIN_ENDPOINTS = {"/api/v1/tenant", "/api/v1/auth", "/api/v1/billing", "/api/v1/scim"}


class EmbedTokenRequest(BaseModel):
    tenant_id: str


class EmbedTokenResponse(BaseModel):
    token: str
    expires_in: int
    scope: str
    permissions: list[str]


@router.post("/embed/token", response_model=EmbedTokenResponse)
async def issue_embed_token(
    req: EmbedTokenRequest,
    db: AsyncSession = Depends(get_async_db),
    _api_key: bool = Depends(verify_api_key),
):
    """Issue a short-lived embed token scoped to a tenant.

    Requires a valid bank credential (X-API-Key header).
    The embed token is a regular JWT with scope='embed' and limited permissions.
    """
    result = await db.execute(select(Tenant).filter(Tenant.tenant_id == req.tenant_id))
    tenant = result.scalars().first()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    if tenant.status != "active":
        raise HTTPException(status_code=403, detail="Tenant is not active")

    token = create_access_token(
        data={
            "sub": f"embed:{tenant.tenant_id}",
            "tenant_id": tenant.tenant_id,
            "scope": "embed",
            "role": "embed",
            "permissions": EMBED_PERMISSIONS,
        },
        expires_delta=EMBED_TOKEN_EXPIRY,
    )

    return EmbedTokenResponse(
        token=token,
        expires_in=int(EMBED_TOKEN_EXPIRY.total_seconds()),
        scope="embed",
        permissions=EMBED_PERMISSIONS,
    )
