"""ML-related Celery tasks.

Thin wrappers around the ML service functions.
"""

import asyncio
import logging

from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


async def _run(func, *args, **kwargs):
    from app.database import AsyncSessionLocal
    async with AsyncSessionLocal() as session:
        return await func(session, *args, **kwargs)


@celery_app.task(
    bind=True,
    name="ml.run_drift_check",
    soft_time_limit=600,
    max_retries=3,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=600,
    retry_jitter=True,
)
def run_drift_check(self):
    """Run model drift detection check."""
    from app.services.ml.drift_worker import run_drift_check as _check
    logger.info("Starting drift check")
    result = asyncio.run(_run(_check))
    logger.info("Drift check complete: %s", result)
    return result
