"""WhatsApp outbound warning sender.

Sends scam warning template messages via the WhatsApp Business Cloud API.
Requires ``whatsapp_outbound_enabled=True`` in config.
"""

import logging

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings

logger = logging.getLogger(__name__)

# Template name registered in WhatsApp Business Manager.
# Document: https://business.facebook.com/wa-business/help/351919382045370
WARNING_TEMPLATE_NAME = "trustshield_scam_warning_v1"


async def send_whatsapp_warning(to: str, summary: str, db: AsyncSession) -> dict:
    """Send a scam warning template message via WhatsApp Business Cloud API.

    Args:
        to: Recipient phone number (E.164 format, e.g. ``+919876543210``).
        summary: Short scam summary for the template parameter.
        db: AsyncSession for audit logging.

    Returns:
        ``{"sent": bool, "status": str}``
    """
    if not settings.whatsapp_outbound_enabled:
        logger.warning("WhatsApp outbound is disabled — skipping send to %s", to)
        _log_attempt(db, to, summary, "failed", "outbound_disabled")
        return {"sent": False, "status": "outbound_disabled"}

    url = f"https://graph.facebook.com/v18.0/{settings.whatsapp_phone_number_id}/messages"
    headers = {
        "Authorization": f"Bearer {settings.whatsapp_access_token}",
        "Content-Type": "application/json",
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "template",
        "template": {
            "name": WARNING_TEMPLATE_NAME,
            "language": {"code": "hi"},
            "components": [
                {
                    "type": "body",
                    "parameters": [{"type": "text", "text": summary}],
                }
            ],
        },
    }

    error_detail = None

    for attempt in range(2):
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.post(url, json=payload, headers=headers)
            if resp.status_code < 300:
                logger.info("WhatsApp warning sent to %s (attempt %d)", to, attempt + 1)
                _log_attempt(db, to, summary, "sent", None)
                return {"sent": True, "status": "sent"}
            error_detail = f"HTTP {resp.status_code}: {resp.text[:200]}"
            logger.warning(
                "WhatsApp send failed (attempt %d): %s", attempt + 1, error_detail
            )
        except httpx.HTTPError as exc:
            error_detail = str(exc)
            logger.warning("WhatsApp send failed (attempt %d): %s", attempt + 1, exc)

    _log_attempt(db, to, summary, "failed", error_detail)
    return {"sent": False, "status": "failed"}


def _log_attempt(
    db: AsyncSession, to: str, summary: str, status: str, error: str | None
) -> None:
    """Fire-and-forget audit log entry for WhatsApp send attempts."""
    try:
        from app.models.intervention import InterventionLog

        detail = f"WhatsApp warning to {to}: {summary}"
        if error:
            detail += f" | error={error}"
        entry = InterventionLog(
            session_id=f"whatsapp-{to}",
            intervention_type="whatsapp_warning",
            status=status,
            details=detail,
        )
        db.add(entry)
    except Exception as exc:
        logger.error("Failed to audit-log WhatsApp send: %s", exc)
