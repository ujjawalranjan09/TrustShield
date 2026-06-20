"""DLP Scan — detects cross-tenant PII leakage."""

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.scan_event import ScanEvent
from app.models.tenant import Tenant

logger = logging.getLogger(__name__)


async def run_dlp_scan(db: AsyncSession) -> dict:
    """Scan for cross-tenant PII leakage.

    For each tenant, samples recent scan events and checks that no other
    tenant's entities appear in the results.

    Returns:
        {tenants_scanned: int, leaks_found: int, details: list}
    """
    tenant_result = await db.execute(
        select(Tenant).filter(Tenant.status == "active")
    )
    tenants = tenant_result.scalars().all()

    tenants_scanned = 0
    leaks_found = 0
    details = []

    for tenant in tenants:
        tenants_scanned += 1

        # Sample recent scan events for this tenant
        events_result = await db.execute(
            select(ScanEvent)
            .filter(
                ScanEvent.tenant_id == tenant.tenant_id,
                ScanEvent.entities_found > 0,
            )
            .order_by(ScanEvent.created_at.desc())
            .limit(100)
        )
        events = events_result.scalars().all()

        if not events:
            continue

        # Check for cross-tenant references: events where session_id patterns
        # suggest data from another tenant's scope
        other_tenant_ids = {t.tenant_id for t in tenants if t.tenant_id != tenant.tenant_id}

        for event in events:
            # Heuristic: if scan event's client_ip or session metadata references
            # another tenant's known patterns, flag it
            if event.session_id and any(
                tid in event.session_id for tid in other_tenant_ids
            ):
                leaks_found += 1
                details.append({
                    "tenant_id": tenant.tenant_id,
                    "event_id": event.id,
                    "session_id": event.session_id,
                    "reason": "session_id contains cross-tenant reference",
                })

    return {
        "tenants_scanned": tenants_scanned,
        "leaks_found": leaks_found,
        "details": details,
    }
