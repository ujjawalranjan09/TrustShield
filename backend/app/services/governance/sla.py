"""SLA Engine — computes uptime, latency, and audit-chain integrity metrics."""

import logging
from datetime import datetime, timezone

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import AuditLog
from app.models.scan_event import ScanEvent

logger = logging.getLogger(__name__)


async def compute_sla_attainment(tenant_id: str, month: int, year: int, db: AsyncSession) -> dict:
    """Compute SLA attainment for a tenant in a given month.

    Returns:
        {
            uptime_pct: float,
            latency_p95_ms: float,
            audit_clean: bool,
            overall_met: bool,
        }
    """
    start_of_month = datetime(year, month, 1, tzinfo=timezone.utc)
    if month == 12:
        end_of_month = datetime(year + 1, 1, 1, tzinfo=timezone.utc)
    else:
        end_of_month = datetime(year, month + 1, 1, tzinfo=timezone.utc)

    # Uptime: ratio of successful scans (risk_score is not None) to total scans
    total_result = await db.execute(
        select(func.count(ScanEvent.id)).filter(
            ScanEvent.tenant_id == tenant_id,
            ScanEvent.created_at >= start_of_month,
            ScanEvent.created_at < end_of_month,
        )
    )
    total_scans = total_result.scalar() or 0

    success_result = await db.execute(
        select(func.count(ScanEvent.id)).filter(
            ScanEvent.tenant_id == tenant_id,
            ScanEvent.created_at >= start_of_month,
            ScanEvent.created_at < end_of_month,
            ScanEvent.risk_score.isnot(None),
        )
    )
    successful_scans = success_result.scalar() or 0

    uptime_pct = (successful_scans / total_scans * 100) if total_scans > 0 else 100.0

    # Latency p95: from processing_time_ms on scan events
    latency_result = await db.execute(
        select(ScanEvent.processing_time_ms)
        .filter(
            ScanEvent.tenant_id == tenant_id,
            ScanEvent.created_at >= start_of_month,
            ScanEvent.created_at < end_of_month,
            ScanEvent.processing_time_ms.isnot(None),
        )
        .order_by(ScanEvent.processing_time_ms)
    )
    latencies = [row[0] for row in latency_result.all()]
    if latencies:
        p95_index = int(len(latencies) * 0.95)
        latency_p95_ms = float(latencies[min(p95_index, len(latencies) - 1)])
    else:
        latency_p95_ms = 0.0

    # Audit chain integrity: check no broken hash chains for this tenant's audit logs
    audit_result = await db.execute(
        select(AuditLog)
        .filter(
            AuditLog.created_at >= start_of_month,
            AuditLog.created_at < end_of_month,
        )
        .order_by(AuditLog.id)
    )
    audit_logs = audit_result.scalars().all()
    audit_clean = True
    for i, log in enumerate(audit_logs):
        if i > 0 and log.prev_hash and audit_logs[i - 1].entry_hash:
            if log.prev_hash != audit_logs[i - 1].entry_hash:
                audit_clean = False
                break

    overall_met = uptime_pct >= 99.0 and latency_p95_ms <= 500.0 and audit_clean

    return {
        "uptime_pct": round(uptime_pct, 2),
        "latency_p95_ms": round(latency_p95_ms, 2),
        "audit_clean": audit_clean,
        "overall_met": overall_met,
    }
