"""Reputation Service — enriched scoring with recency, rings, graph risk, cross-bank data."""

import hashlib
import logging
import math
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.entity import FlaggedEntity
from app.models.intel import SharedEntity
from app.models.ring import FraudRing

logger = logging.getLogger(__name__)

RECENCY_WINDOWS = [
    (7, 1.0),
    (30, 0.7),
    (90, 0.4),
    (180, 0.2),
]


def _recency_weight(last_seen: datetime | None) -> float:
    if last_seen is None:
        return 0.1
    now = datetime.now(timezone.utc)
    if last_seen.tzinfo is None:
        last_seen = last_seen.replace(tzinfo=timezone.utc)
    days = (now - last_seen).days
    for window, weight in RECENCY_WINDOWS:
        if days <= window:
            return weight
    return 0.1


def _tier(score: int) -> str:
    if score >= 80:
        return "confirmed_scam"
    if score >= 50:
        return "suspicious"
    if score >= 20:
        return "watch"
    return "clean"


def _mask_entity(entity_value: str) -> str:
    if len(entity_value) <= 4:
        return entity_value[0] + "***"
    return entity_value[:3] + "***" + entity_value[-2:]


async def _get_propagated_risk(entity_value: str) -> float:
    try:
        from app.services.graph.entity_graph import FraudEntityGraph
        graph = FraudEntityGraph()
        try:
            risk = await graph.get_entity_risk(entity_value)
            return risk
        finally:
            await graph.close()
    except Exception:
        return 0.0


async def _get_ring_info(entity_value: str) -> dict:
    try:
        from app.services.graph.entity_graph import FraudEntityGraph
        graph = FraudEntityGraph()
        try:
            if not graph.connected:
                return {"ring_id": None, "ring_status": None, "ring_risk": None}
            await graph._ensure_connected()
            if not graph.connected or not graph.driver:
                return {"ring_id": None, "ring_status": None, "ring_risk": None}
            query = """
            MATCH (n:Entity {value: $value})
            RETURN n.ring_id AS ring_id
            """
            async with graph.driver.session() as session:
                result = await session.run(query, value=entity_value)
                record = await result.single()
                if not record or not record["ring_id"]:
                    return {"ring_id": None, "ring_status": None, "ring_risk": None}
                ring_id = record["ring_id"]
        finally:
            await graph.close()

        from app.database import AsyncSessionLocal
        async with AsyncSessionLocal() as db:
            ring_result = await db.execute(
                select(FraudRing).filter(FraudRing.ring_id == ring_id)
            )
            ring = ring_result.scalars().first()
            if not ring:
                return {"ring_id": ring_id, "ring_status": None, "ring_risk": None}
            return {
                "ring_id": ring_id,
                "ring_status": ring.status,
                "ring_risk": ring.risk_level,
            }
    except Exception:
        return {"ring_id": None, "ring_status": None, "ring_risk": None}


async def compute_reputation(entity_value: str, entity_type: str, db: AsyncSession) -> dict:
    """Compute reputation for an entity, using cross-cell federation when available."""
    from app.config import settings

    if settings.cell_routing_enabled:
        try:
            from app.services.intel.cell_federation import federated_reputation_lookup
            return await federated_reputation_lookup(entity_value, entity_type, db)
        except Exception as exc:
            logger.warning("Federation unavailable, falling back to local reputation: %s", exc)

    return await _compute_local_reputation(entity_value, entity_type, db)


async def _compute_local_reputation(entity_value: str, entity_type: str, db: AsyncSession) -> dict:
    entity_key = f"{entity_type}:{entity_value.lower().strip()}"
    entity_hash = hashlib.sha256(entity_value.lower().strip().encode()).hexdigest()[:32]

    result = await db.execute(
        select(FlaggedEntity).filter(FlaggedEntity.entity_value == entity_key)
    )
    entity = result.scalars().first()

    cross_result = await db.execute(
        select(SharedEntity).filter(SharedEntity.entity_hash == entity_hash)
    )
    cross_bank = cross_result.scalars().first()

    report_count = entity.report_count if entity else 0
    last_seen = entity.last_seen if entity else None
    first_seen = entity.first_reported if entity else None
    banks_reporting = cross_bank.banks_reporting if cross_bank else 0

    recency_w = _recency_weight(last_seen)
    base_score = min(50, math.log(1 + report_count) * 10) * recency_w

    propagated_risk = await _get_propagated_risk(entity_key)
    propagated_component = propagated_risk * 30

    ring_info = await _get_ring_info(entity_key)
    ring_bump = 0
    if ring_info.get("ring_status") == "confirmed":
        ring_bump = 25
    elif ring_info.get("ring_id"):
        ring_bump = 15

    cross_bank_bump = min(20, banks_reporting * 5)

    raw_score = base_score + ring_bump + propagated_component + cross_bank_bump
    score = max(0, min(100, int(raw_score)))

    return {
        "entity": entity_value,
        "reputation_tier": _tier(score),
        "score": score,
        "direct_reports": report_count,
        "propagated_risk": round(propagated_risk, 4),
        "ring_membership": ring_info.get("ring_id"),
        "last_reported_at": last_seen.isoformat() if last_seen else None,
        "first_seen": first_seen.isoformat() if first_seen else None,
    }


async def get_public_reputation(entity_value: str, entity_type: str, db: AsyncSession) -> dict:
    full = await compute_reputation(entity_value, entity_type, db)
    score = full["score"]
    report_count = full["direct_reports"]
    if report_count == 0:
        count_bucket = "none"
    elif report_count <= 2:
        count_bucket = "few"
    elif report_count <= 10:
        count_bucket = "several"
    else:
        count_bucket = "many"
    return {
        "entity": _mask_entity(entity_value),
        "reputation_tier": full["reputation_tier"],
        "score": score,
        "report_count_bucket": count_bucket,
    }
