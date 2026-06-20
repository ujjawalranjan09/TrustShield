"""Tenant management API endpoints."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user, require_role
from app.database import get_async_db
from app.models.tenant import Tenant
from app.models.user import User
from app.services.tenant.lifecycle import provision_tenant, offboard_tenant

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/tenant", tags=["Tenant"])


class ProvisionRequest(BaseModel):
    slug: str
    tier: str = "bank"
    display_name: str
    region: str = "ap-south-1"


@router.post("/provision")
async def provision(
    req: ProvisionRequest,
    db: AsyncSession = Depends(get_async_db),
    _admin: User = Depends(require_role("super_admin")),
):
    """Provision a new tenant (super_admin only)."""
    existing = await db.execute(select(Tenant).filter(Tenant.slug == req.slug))
    if existing.scalars().first():
        raise HTTPException(status_code=409, detail="Tenant slug already exists")
    tenant = await provision_tenant(
        slug=req.slug,
        tier=req.tier,
        display_name=req.display_name,
        region=req.region,
        db=db,
    )
    return {"tenant_id": tenant.tenant_id, "slug": tenant.slug, "status": tenant.status}


@router.post("/{tenant_id}/offboard")
async def offboard(
    tenant_id: str,
    db: AsyncSession = Depends(get_async_db),
    _admin: User = Depends(require_role("super_admin")),
):
    """Offboard a tenant (super_admin only). Retention holds apply."""
    await offboard_tenant(tenant_id, db)
    return {"tenant_id": tenant_id, "status": "offboarding"}


@router.get("/{tenant_id}")
async def get_tenant(
    tenant_id: str,
    db: AsyncSession = Depends(get_async_db),
    _user: User = Depends(get_current_user),
):
    """Get tenant details."""
    result = await db.execute(select(Tenant).filter(Tenant.tenant_id == tenant_id))
    tenant = result.scalars().first()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    return {
        "tenant_id": tenant.tenant_id,
        "slug": tenant.slug,
        "display_name": tenant.display_name,
        "tier": tenant.tier,
        "status": tenant.status,
        "data_region": tenant.data_region,
        "created_at": tenant.created_at.isoformat() if tenant.created_at else None,
    }
