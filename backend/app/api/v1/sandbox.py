"""Integration Sandbox API — creates isolated sandbox tenants with synthetic data."""

import json
import logging
import secrets
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import verify_api_key
from app.database import get_async_db
from app.models.recovery import RecoveryCase
from app.models.ring import FraudRing
from app.models.scan_event import ScanEvent
from app.models.tenant import Tenant

logger = logging.getLogger(__name__)

router = APIRouter()


class SandboxSignupResponse(BaseModel):
    tenant_id: str
    api_key: str
    slug: str


class SandboxStatusResponse(BaseModel):
    status: str
    tenant_id: str
    scan_events: int
    fraud_rings: int
    recovery_cases: int


async def _seed_sandbox_data(tenant_id: str, db: AsyncSession) -> None:
    """Create synthetic scan events, a fraud ring, and a recovery case."""
    now = datetime.now(timezone.utc)
    risk_levels = ["LOW", "MEDIUM", "HIGH", "CRITICAL"]
    scan_types = ["analyze", "scan-message", "webhook"]

    for i in range(20):
        event = ScanEvent(
            tenant_id=tenant_id,
            session_id=f"sandbox-session-{i:03d}",
            scan_type=scan_types[i % len(scan_types)],
            risk_score=(i * 5) % 100,
            risk_level=risk_levels[i % len(risk_levels)],
            action_taken="blocked" if i % 3 == 0 else "allowed",
            entities_found=i % 5,
            processing_time_ms=50 + (i * 10),
            client_ip=f"192.168.1.{i + 1}",
            created_at=now,
        )
        db.add(event)

    ring = FraudRing(
        ring_id=f"sandbox-ring-{secrets.token_hex(4)}",
        entity_count=5,
        total_reports=12,
        top_scam_type="UPI_FRAUD",
        risk_level="high",
        avg_pagerank=75,
        status="new",
    )
    db.add(ring)

    case = RecoveryCase(
        case_id=f"sandbox-case-{secrets.token_hex(4)}",
        tenant_id=tenant_id,
        fraud_type="UPI_FRAUD",
        amount_lost=15000.0,
        scammer_info=json.dumps({"upi_id": "scammer@bank", "phone": "9876543210"}),
        incident_date="2026-06-15",
        victim_name="Test Victim",
        victim_phone="9000000000",
        bank_name="Test Bank",
        upi_id="victim@bank",
        current_step=2,
        total_steps=6,
        status="in_progress",
    )
    db.add(case)
    await db.commit()


@router.post("/sandbox/signup", response_model=SandboxSignupResponse)
async def sandbox_signup(
    db: AsyncSession = Depends(get_async_db),
    _api_key: bool = Depends(verify_api_key),
):
    """Create a sandbox tenant with seeded synthetic data and return API keys."""
    slug = f"sandbox-{secrets.token_hex(4)}"
    tenant = Tenant(
        slug=slug,
        display_name="Sandbox Tenant",
        tier="bank",
        status="active",
        data_region="ap-south-1",
        is_sandbox=True,
    )
    db.add(tenant)
    await db.commit()
    await db.refresh(tenant)

    await _seed_sandbox_data(tenant.tenant_id, db)

    api_key = f"ts_sandbox_{secrets.token_urlsafe(32)}"
    logger.info("Sandbox tenant created: %s", tenant.tenant_id)

    return SandboxSignupResponse(
        tenant_id=tenant.tenant_id,
        api_key=api_key,
        slug=slug,
    )


@router.post("/sandbox/reset")
async def sandbox_reset(
    tenant_id: str,
    db: AsyncSession = Depends(get_async_db),
    _api_key: bool = Depends(verify_api_key),
):
    """Clear and re-seed sandbox data for a tenant."""
    result = await db.execute(select(Tenant).filter(Tenant.tenant_id == tenant_id))
    tenant = result.scalars().first()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    if not tenant.is_sandbox:
        raise HTTPException(status_code=403, detail="Tenant is not a sandbox tenant")

    # Clear existing data
    from sqlalchemy import delete
    await db.execute(delete(ScanEvent).where(ScanEvent.tenant_id == tenant_id))
    await db.execute(delete(FraudRing).where(FraudRing.ring_id.like("sandbox-ring-%")))
    await db.execute(delete(RecoveryCase).where(RecoveryCase.tenant_id == tenant_id))
    await db.commit()

    # Re-seed
    await _seed_sandbox_data(tenant_id, db)

    return {"status": "reset", "tenant_id": tenant_id}


@router.get("/sandbox/status", response_model=SandboxStatusResponse)
async def sandbox_status(
    tenant_id: str,
    db: AsyncSession = Depends(get_async_db),
    _api_key: bool = Depends(verify_api_key),
):
    """Return sandbox health and data stats."""
    result = await db.execute(select(Tenant).filter(Tenant.tenant_id == tenant_id))
    tenant = result.scalars().first()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    if not tenant.is_sandbox:
        raise HTTPException(status_code=403, detail="Tenant is not a sandbox tenant")

    scan_count = await db.execute(
        select(func.count()).select_from(ScanEvent).where(ScanEvent.tenant_id == tenant_id)
    )
    ring_count = await db.execute(
        select(func.count()).select_from(FraudRing).where(FraudRing.ring_id.like("sandbox-ring-%"))
    )
    case_count = await db.execute(
        select(func.count()).select_from(RecoveryCase).where(RecoveryCase.tenant_id == tenant_id)
    )

    return SandboxStatusResponse(
        status="healthy",
        tenant_id=tenant_id,
        scan_events=scan_count.scalar() or 0,
        fraud_rings=ring_count.scalar() or 0,
        recovery_cases=case_count.scalar() or 0,
    )
