"""Ingest normalizer — canonical event fanout.

Takes any incoming signal (analyze, report, webhook, voice, image),
normalizes it into an IntelEvent, and fans out asynchronously to four
sinks: graph writer, reputation updater, intervention evaluator,
and proactive intervention evaluator.
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field

from app.schemas.analyze import ScamType
from app.schemas.entity import EntityType

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Canonical event model
# ---------------------------------------------------------------------------


class IntelEvent(BaseModel):
    entity_value: str
    entity_type: EntityType
    scam_type: ScamType = ScamType.UNKNOWN
    risk: float = Field(ge=0, le=100, default=0)
    source: str
    session_id: str
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    geo: Optional[Dict[str, Any]] = None


# ---------------------------------------------------------------------------
# Normalization — one extractor per event type
# ---------------------------------------------------------------------------

_RISK_LEVEL_MAP = {
    "critical": 90.0,
    "high": 70.0,
    "medium": 45.0,
    "low": 15.0,
}


def _normalize_analyze(payload: dict) -> IntelEvent:
    session_meta = payload.get("session_metadata", payload)
    session_id = session_meta.get("session_id", "unknown")

    entities = payload.get("entities") or payload.get("flagged_entities", [])
    first_entity = entities[0] if entities else {}
    entity_value = first_entity.get("value", session_id)
    raw_etype = first_entity.get("entity_type", "PHONE")
    entity_type = EntityType(raw_etype) if raw_etype in EntityType.__members__.values() else EntityType.PHONE

    raw_scam = payload.get("scam_type", "unknown")
    scam_type = ScamType(raw_scam) if raw_scam in ScamType.__members__.values() else ScamType.UNKNOWN

    risk = float(payload.get("risk_score", payload.get("risk", 0)))
    geo = payload.get("geo_location")

    return IntelEvent(
        entity_value=entity_value,
        entity_type=entity_type,
        scam_type=scam_type,
        risk=min(max(risk, 0), 100),
        source="analyze",
        session_id=session_id,
        geo=geo,
    )


def _normalize_report(payload: dict) -> IntelEvent:
    raw_etype = payload.get("entity_type", "PHONE")
    entity_type = EntityType(raw_etype) if raw_etype in EntityType.__members__.values() else EntityType.PHONE

    raw_scam = payload.get("scam_type", "unknown")
    scam_type = ScamType(raw_scam) if raw_scam in ScamType.__members__.values() else ScamType.UNKNOWN

    report_count = payload.get("report_count", 1)
    risk = min(100.0, report_count * 10.0)

    return IntelEvent(
        entity_value=payload.get("entity_value", "unknown"),
        entity_type=entity_type,
        scam_type=scam_type,
        risk=risk,
        source="report",
        session_id=payload.get("session_id", f"report-{payload.get('report_id', 'unknown')}"),
    )


def _normalize_webhook(payload: dict) -> IntelEvent:
    risk = float(payload.get("risk_score", 0))

    amount = payload.get("amount", 0)
    if amount > 50000:
        risk = max(risk, 70.0)
    if payload.get("payer_vpa") == payload.get("payee_vpa"):
        risk = max(risk, 80.0)

    return IntelEvent(
        entity_value=payload.get("payee_vpa", "unknown"),
        entity_type=EntityType.UPI,
        scam_type=ScamType.PHISHING if risk >= 50 else ScamType.UNKNOWN,
        risk=min(max(risk, 0), 100),
        source="webhook",
        session_id=payload.get("session_id", f"webhook-{payload.get('payer_vpa', 'unknown')}"),
        geo=payload.get("geo_location"),
    )


def _normalize_voice(payload: dict) -> IntelEvent:
    entities = payload.get("entities") or payload.get("flagged_entities", [])
    first_entity = entities[0] if entities else {}
    entity_value = first_entity.get("value") or payload.get("caller_id", "unknown")

    raw_etype = first_entity.get("entity_type", "PHONE")
    entity_type = EntityType(raw_etype) if raw_etype in EntityType.__members__.values() else EntityType.PHONE

    raw_scam = payload.get("scam_type", "unknown")
    scam_type = ScamType(raw_scam) if raw_scam in ScamType.__members__.values() else ScamType.UNKNOWN

    risk = float(payload.get("risk_score", payload.get("risk", 0)))

    return IntelEvent(
        entity_value=entity_value,
        entity_type=entity_type,
        scam_type=scam_type,
        risk=min(max(risk, 0), 100),
        source="voice",
        session_id=payload.get("session_id", f"voice-{entity_value}"),
    )


def _normalize_image(payload: dict) -> IntelEvent:
    qr_codes = payload.get("qr_codes", [])
    suspicious_qr = next(
        (qr for qr in qr_codes if qr.get("is_suspicious")),
        qr_codes[0] if qr_codes else {},
    )
    entity_value = suspicious_qr.get("content", payload.get("image_hash", "unknown"))
    entity_type_str = "URL_SHORTLINK" if suspicious_qr.get("content_type") == "url" else "APK"
    raw_etype = payload.get("entity_type", entity_type_str)
    entity_type = EntityType(raw_etype) if raw_etype in EntityType.__members__.values() else EntityType.URL_SHORTLINK

    raw_level = payload.get("risk_level", "low")
    risk = _RISK_LEVEL_MAP.get(raw_level, 15.0)

    raw_scam = payload.get("scam_type", "unknown")
    scam_type = ScamType(raw_scam) if raw_scam in ScamType.__members__.values() else ScamType.UNKNOWN

    return IntelEvent(
        entity_value=entity_value,
        entity_type=entity_type,
        scam_type=scam_type,
        risk=min(max(risk, 0), 100),
        source="image",
        session_id=payload.get("session_id", f"image-{payload.get('image_hash', 'unknown')}"),
    )


_NORMALIZERS = {
    "analyze": _normalize_analyze,
    "report": _normalize_report,
    "webhook": _normalize_webhook,
    "voice": _normalize_voice,
    "image": _normalize_image,
}


# ---------------------------------------------------------------------------
# Sink functions — each publishes to its topic and never raises
# ---------------------------------------------------------------------------


async def _emit_to_graph(event: IntelEvent) -> None:
    try:
        from app.services.events.publisher import get_event_publisher
        publisher = get_event_publisher()
        await publisher.publish("intel.graph", "graph_writer", event.model_dump(mode="json"))
        logger.debug("Published to graph sink: %s", event.entity_value)
    except Exception as exc:
        logger.error("Graph sink failed for %s: %s", event.entity_value, exc)


async def _emit_to_reputation(event: IntelEvent) -> None:
    try:
        from app.services.events.publisher import get_event_publisher
        publisher = get_event_publisher()
        await publisher.publish("intel.reputation", "reputation_updater", event.model_dump(mode="json"))
        logger.debug("Published to reputation sink: %s", event.entity_value)
    except Exception as exc:
        logger.error("Reputation sink failed for %s: %s", event.entity_value, exc)


async def _emit_to_intervention(event: IntelEvent) -> None:
    try:
        from app.services.events.publisher import get_event_publisher
        publisher = get_event_publisher()
        await publisher.publish("intel.intervention", "intervention_evaluator", event.model_dump(mode="json"))
        logger.debug("Published to intervention sink: %s", event.entity_value)
    except Exception as exc:
        logger.error("Intervention sink failed for %s: %s", event.entity_value, exc)


async def _emit_to_proactive_intervention(event: IntelEvent) -> None:
    try:
        from app.database import AsyncSessionLocal
        from app.services.intervention.action_engine import evaluate_intervention

        async with AsyncSessionLocal() as db:
            await evaluate_intervention(event.model_dump(mode="json"), db)
    except Exception as exc:
        logger.error("Proactive intervention evaluator failed for %s: %s", event.entity_value, exc)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def normalize_and_emit(
    event_type: str,
    payload: dict,
    db: Any,
) -> IntelEvent:
    """Normalize an incoming signal and fan out to four sinks.

    Args:
        event_type: One of "analyze", "report", "webhook", "voice", "image".
        payload: The raw event payload (shape varies by event_type).
        db: AsyncSession (accepted for forward-compatibility; not used yet).

    Returns:
        The canonical IntelEvent produced from the payload.
    """
    normalizer = _NORMALIZERS.get(event_type)
    if normalizer is None:
        raise ValueError(f"Unknown event_type: {event_type!r}. Expected one of: {list(_NORMALIZERS)}")

    event = normalizer(payload)

    asyncio.create_task(_emit_to_graph(event))
    asyncio.create_task(_emit_to_reputation(event))
    asyncio.create_task(_emit_to_intervention(event))
    asyncio.create_task(_emit_to_proactive_intervention(event))

    return event
