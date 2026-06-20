"""Bank freeze/hold channel.

Sends freeze-hold requests to partner banks via configured webhooks
and logs every attempt in the InterventionLog.
"""

import json
import logging

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.intel import Bank
from app.models.intervention import InterventionLog

logger = logging.getLogger(__name__)


async def send_freeze_request(
    case_id: str,
    victim_entity: str,
    risk: float,
    recommended_action: str,
    ttl_seconds: int,
    db: AsyncSession,
) -> dict:
    """Send a freeze/hold request to the victim's bank.

    Args:
        case_id: Unique case identifier (idempotency key).
        victim_entity: Masked victim identifier (phone / VPA).
        risk: Risk score that triggered the freeze.
        recommended_action: Recommended bank action (e.g. ``"hold"``).
        ttl_seconds: How long the freeze should remain active.
        db: Async database session.

    Returns:
        ``{"status": "sent"|"dashboard_only", "bank_id": str}``
    """
    result = await db.execute(
        select(Bank).limit(1)
    )
    bank = result.scalar_one_or_none()

    if bank is None:
        _log_intervention(
            db, case_id, "bank_freeze_request", "failed",
            f"No bank found for case {case_id}",
        )
        return {"status": "error", "reason": "no_bank_found"}

    if not bank.freeze_webhook_url:
        _log_intervention(
            db, case_id, "bank_freeze_request", "dashboard_only",
            f"No webhook configured for bank {bank.bank_id}",
        )
        return {"status": "dashboard_only", "bank_id": bank.bank_id, "reason": "no webhook configured"}

    payload = {
        "case_id": case_id,
        "victim_entity": victim_entity,
        "risk": risk,
        "recommended_action": "hold",
        "ttl_seconds": ttl_seconds,
    }

    status = "sent"
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                bank.freeze_webhook_url,
                content=json.dumps(payload),
                headers={"Content-Type": "application/json"},
            )
        if resp.status_code >= 300:
            status = "failed"
            logger.warning(
                "Bank freeze webhook returned %d for case %s",
                resp.status_code,
                case_id,
            )
    except httpx.HTTPError as exc:
        status = "failed"
        logger.warning("Bank freeze webhook failed for case %s: %s", case_id, exc)

    _log_intervention(
        db, case_id, "bank_freeze_request", status,
        f"Freeze request for {victim_entity} via bank {bank.bank_id}",
    )
    return {"status": status, "bank_id": bank.bank_id}


def _log_intervention(
    db: AsyncSession,
    case_id: str,
    intervention_type: str,
    status: str,
    details: str,
) -> None:
    """Append an InterventionLog entry (fire-and-forget safe)."""
    try:
        entry = InterventionLog(
            session_id=case_id,
            intervention_type=intervention_type,
            status=status,
            details=details,
        )
        db.add(entry)
    except Exception as exc:
        logger.error("Failed to log intervention: %s", exc)
