"""Billing-related Celery tasks.

Thin wrappers around the billing service functions.
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
    name="billing.nightly_rollup",
    soft_time_limit=300,
    max_retries=3,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=600,
    retry_jitter=True,
)
def nightly_usage_rollup(self):
    """Nightly usage rollup — aggregates metered usage for billing."""
    from app.services.billing.jobs import nightly_usage_rollup as _rollup
    logger.info("Starting nightly usage rollup")
    result = asyncio.run(_run(_rollup))
    logger.info("Nightly usage rollup complete: %s", result)
    return result


@celery_app.task(
    bind=True,
    name="billing.submit_stripe_metering",
    soft_time_limit=300,
    max_retries=3,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=600,
    retry_jitter=True,
)
def submit_stripe_metering(self):
    """Submit metered usage to Stripe."""
    from app.services.billing.jobs import submit_stripe_metering as _submit
    logger.info("Submitting Stripe metering")
    result = asyncio.run(_run(_submit))
    logger.info("Stripe metering submitted: %s", result)
    return result


@celery_app.task(
    bind=True,
    name="billing.purge_old_usage_events",
    soft_time_limit=600,
    max_retries=3,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=600,
    retry_jitter=True,
)
def purge_old_usage_events(self):
    """Purge old usage events beyond retention period."""
    from app.services.billing.jobs import purge_old_usage_events as _purge
    logger.info("Purging old usage events")
    result = asyncio.run(_run(_purge))
    logger.info("Usage event purge complete: %s", result)
    return result
