"""Reputation refresh & decay Celery tasks.

Nightly job that recomputes reputation for all entities with recent activity
and decays scores for entities whose reports are old.
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.config import settings
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


async def _reputation_refresh() -> dict:
    from app.database import AsyncSessionLocal
    from app.models.entity import FlaggedEntity
    from app.services.intel.reputation_service import compute_reputation

    cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    updated = 0
    skipped = 0

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(FlaggedEntity).filter(
                FlaggedEntity.last_seen >= cutoff
            )
        )
        entities = result.scalars().all()

        for entity in entities:
            try:
                await compute_reputation(entity.entity_value, entity.entity_type, db)
                updated += 1
            except Exception as e:
                logger.warning("Failed to refresh reputation for %s: %s", entity.entity_value, e)
                skipped += 1

    return {"status": "success", "entities_refreshed": updated, "skipped": skipped}


async def _reputation_decay() -> dict:
    from app.database import AsyncSessionLocal
    from app.models.entity import FlaggedEntity

    decay_cutoff = datetime.now(timezone.utc) - timedelta(days=settings.reputation_decay_days)

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(FlaggedEntity).filter(
                FlaggedEntity.last_seen < decay_cutoff,
                FlaggedEntity.report_count > 0,
            )
        )
        entities = result.scalars().all()
        decayed = 0

        for entity in entities:
            entity.report_count = max(0, entity.report_count - 1)
            if entity.report_count == 0:
                entity.is_confirmed = 0
            decayed += 1

        await db.commit()

    return {"status": "success", "entities_decayed": decayed}


@celery_app.task(name="app.workers.tasks.reputation_tasks.reputation_refresh")
def reputation_refresh() -> dict:
    return asyncio.run(_reputation_refresh())


@celery_app.task(name="app.workers.tasks.reputation_tasks.reputation_decay")
def reputation_decay() -> dict:
    return asyncio.run(_reputation_decay())
