"""Alert service for high-risk fraud detections.

Sends alerts via webhook callbacks and logs. Designed to be extended
with email, Slack, Teams, and SMS integrations.
"""

import logging
import os
from typing import List, Optional

import httpx

logger = logging.getLogger(__name__)

ALERT_WEBHOOK_URL = os.getenv("ALERT_WEBHOOK_URL", "")
ALERT_THRESHOLD_SCORE = int(os.getenv("ALERT_THRESHOLD_SCORE", "70"))


async def trigger_alert(
    session_id: str,
    risk_score: int,
    risk_level: str,
    action: str,
    entities: List[str],
) -> None:
    """Trigger an alert for a high-risk fraud detection.

    Logs the alert and optionally sends to a webhook URL.
    """
    alert_data = {
        "session_id": session_id,
        "risk_score": risk_score,
        "risk_level": risk_level,
        "action": action,
        "entities": entities,
        "source": "trustshield",
    }

    logger.warning(
        "FRAUD_ALERT session=%s score=%d level=%s action=%s entities=%s",
        session_id, risk_score, risk_level, action, entities,
    )

    if ALERT_WEBHOOK_URL:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.post(ALERT_WEBHOOK_URL, json=alert_data)
                if resp.status_code >= 400:
                    logger.error("Alert webhook failed: %d %s", resp.status_code, resp.text[:200])
                else:
                    logger.info("Alert sent to webhook for session %s", session_id)
        except Exception as e:
            logger.error("Alert webhook error: %s", e)
