"""Signed outbound webhook dispatcher.

Dispatches events to tenant webhook subscriptions with HMAC-SHA256 signatures,
exponential backoff retry, and automatic subscription disabling on persistent failure.
"""

import asyncio
import hashlib
import hmac
import json
import logging
import time
from typing import Any, Dict, List, Optional

import httpx
from sqlalchemy import Column, Boolean, DateTime, Integer, String, Text
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timezone

from app.database import Base

logger = logging.getLogger(__name__)

MAX_RETRIES = 8
REPLAY_TOLERANCE_SECONDS = 300  # 5 minutes


class WebhookSubscription(Base):
    """Persisted webhook subscription for a tenant."""

    __tablename__ = "webhook_subscriptions"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(String(64), nullable=False, index=True)
    url = Column(String(2048), nullable=False)
    event_types = Column(Text, nullable=False)  # JSON list stored as text
    secret = Column(String(256), nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    @property
    def event_type_list(self) -> List[str]:
        return json.loads(self.event_types)


def compute_signature(secret: str, payload: str, timestamp: int) -> str:
    """Compute HMAC-SHA256 signature: v1=<hmac-sha256(secret, t=<ts>|<payload)>."""
    sign_content = f"t={timestamp}|{payload}"
    mac = hmac.new(
        key=secret.encode("utf-8"),
        msg=sign_content.encode("utf-8"),
        digestmod=hashlib.sha256,
    )
    return f"v1={mac.hexdigest()}"


def build_signature_header(secret: str, payload: str, timestamp: int) -> str:
    """Build the full X-TrustShield-Signature header value."""
    sig = compute_signature(secret, payload, timestamp)
    return f"t={timestamp},{sig}"


def verify_signature(secret: str, body: str, signature_header: str) -> bool:
    """Verify an incoming webhook signature.

    Args:
        secret: The subscription secret.
        body: The raw request body string.
        signature_header: The value of X-TrustShield-Signature header.

    Returns:
        True if the signature is valid and timestamp is within tolerance.
    """
    try:
        parts = dict(item.split("=", 1) for item in signature_header.split(","))
        timestamp = int(parts["t"])
        received_sig = parts["v1"]
    except (ValueError, KeyError):
        return False

    now = int(time.time())
    if abs(now - timestamp) > REPLAY_TOLERANCE_SECONDS:
        logger.warning("Webhook signature rejected: timestamp outside tolerance")
        return False

    expected = compute_signature(secret, body, timestamp)
    expected_value = expected.split("=", 1)[1]
    return hmac.compare_digest(received_sig, expected_value)


async def dispatch_event(
    tenant_id: str,
    event_type: str,
    payload: Dict[str, Any],
    db: AsyncSession,
) -> None:
    """Dispatch an event to all matching active subscriptions for a tenant.

    For each subscription:
    1. Query active subscriptions matching event_type
    2. Compute HMAC-SHA256 signature
    3. POST to subscription URL
    4. On failure: retry with exponential backoff (up to MAX_RETRIES)
    5. After max retries: disable subscription + log warning
    6. On success: log to audit
    """
    result = await db.execute(
        __import__("sqlalchemy", fromlist=["select"]).select(WebhookSubscription).filter(
            WebhookSubscription.tenant_id == tenant_id,
            WebhookSubscription.is_active == True,  # noqa: E712
        )
    )
    subscriptions = result.scalars().all()

    payload_str = json.dumps(payload, default=str)
    timestamp = int(time.time())

    for sub in subscriptions:
        event_types = sub.event_type_list
        if event_type not in event_types:
            continue

        sig_header = build_signature_header(sub.secret, payload_str, timestamp)

        success = False
        last_error: Optional[Exception] = None

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    response = await client.post(
                        sub.url,
                        content=payload_str,
                        headers={
                            "Content-Type": "application/json",
                            "X-TrustShield-Signature": sig_header,
                        },
                    )
                    if response.status_code < 300:
                        success = True
                        break
                    last_error = RuntimeError(f"HTTP {response.status_code}")
            except Exception as e:
                last_error = e

            if attempt < MAX_RETRIES:
                backoff = min(2 ** (attempt - 1), 128)
                await asyncio.sleep(backoff)

        if success:
            logger.info(
                "Webhook delivered: tenant=%s event=%s url=%s",
                tenant_id,
                event_type,
                sub.url,
            )
        else:
            sub.is_active = False
            await db.commit()
            logger.warning(
                "Webhook disabled after %d retries: tenant=%s event=%s url=%s error=%s",
                MAX_RETRIES,
                tenant_id,
                event_type,
                sub.url,
                last_error,
            )
