"""Governance API — SLA attainment, change management, and compliance endpoints."""

import json
import logging

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user, require_role
from app.database import get_async_db
from app.models.user import User
from app.services.governance.change_mgmt import ChangeRecord, record_deploy
from app.services.governance.sla import compute_sla_attainment

logger = logging.getLogger(__name__)

router = APIRouter()


class SLAResponse(BaseModel):
    tenant_id: str
    month: int
    year: int
    uptime_pct: float
    latency_p95_ms: float
    audit_clean: bool
    overall_met: bool


class DeployRequest(BaseModel):
    version: str
    git_sha: str
    deployer: str
    summary: str
    affected_tenants: list[str] = Field(default_factory=list)
    risk_level: str = "low"
    sunset_date: str | None = None


class ChangeRecordResponse(BaseModel):
    id: int
    version: str
    git_sha: str
    deployer: str
    summary: str
    affected_tenants: list[str] | None
    risk_level: str
    sunset_date: str | None
    created_at: str


@router.get("/governance/sla/{tenant_id}", response_model=SLAResponse)
async def get_sla(
    tenant_id: str,
    db: AsyncSession = Depends(get_async_db),
    _user: User = Depends(get_current_user),
):
    """Returns SLA attainment for the current month."""
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    result = await compute_sla_attainment(tenant_id, now.month, now.year, db)

    return SLAResponse(
        tenant_id=tenant_id,
        month=now.month,
        year=now.year,
        uptime_pct=result["uptime_pct"],
        latency_p95_ms=result["latency_p95_ms"],
        audit_clean=result["audit_clean"],
        overall_met=result["overall_met"],
    )


@router.post("/governance/changes", response_model=ChangeRecordResponse)
async def create_change(
    req: DeployRequest,
    db: AsyncSession = Depends(get_async_db),
    _admin: User = Depends(require_role("super_admin")),
):
    """Record a deploy (platform_admin only)."""
    sunset_dt = None
    if req.sunset_date:
        from datetime import datetime as dt

        sunset_dt = dt.fromisoformat(req.sunset_date.replace("Z", "+00:00"))

    record = await record_deploy(
        version=req.version,
        git_sha=req.git_sha,
        deployer=req.deployer,
        summary=req.summary,
        db=db,
        affected_tenants=json.dumps(req.affected_tenants) if req.affected_tenants else None,
        risk_level=req.risk_level,
        sunset_date=sunset_dt,
    )

    return ChangeRecordResponse(
        id=record.id,
        version=record.version,
        git_sha=record.git_sha,
        deployer=record.deployer,
        summary=record.summary,
        affected_tenants=json.loads(record.affected_tenants) if record.affected_tenants else None,
        risk_level=record.risk_level,
        sunset_date=record.sunset_date.isoformat() if record.sunset_date else None,
        created_at=record.created_at.isoformat() if record.created_at else None,
    )


@router.get("/governance/changes", response_model=list[ChangeRecordResponse])
async def list_changes(
    db: AsyncSession = Depends(get_async_db),
    _user: User = Depends(get_current_user),
):
    """List change records."""
    result = await db.execute(
        select(ChangeRecord).order_by(ChangeRecord.created_at.desc()).limit(100)
    )
    records = result.scalars().all()

    return [
        ChangeRecordResponse(
            id=r.id,
            version=r.version,
            git_sha=r.git_sha,
            deployer=r.deployer,
            summary=r.summary,
            affected_tenants=json.loads(r.affected_tenants) if r.affected_tenants else None,
            risk_level=r.risk_level,
            sunset_date=r.sunset_date.isoformat() if r.sunset_date else None,
            created_at=r.created_at.isoformat() if r.created_at else None,
        )
        for r in records
    ]
