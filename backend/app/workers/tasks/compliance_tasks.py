"""Compliance-related Celery tasks.

Thin wrappers around the compliance service functions.
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
    name="compliance.verify_audit_chain_window",
    soft_time_limit=300,
    max_retries=3,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=600,
    retry_jitter=True,
)
def verify_audit_chain_window(self):
    """Verify audit chain integrity for the last 24 hours."""
    from app.services.audit import verify_chain_window as _verify
    logger.info("Verifying audit chain (24h window)")
    result = asyncio.run(_run(_verify, hours=24))
    logger.info("Audit chain verification complete: %s", result)
    return result


@celery_app.task(
    bind=True,
    name="compliance.verify_audit_chain_full",
    soft_time_limit=3600,
    max_retries=3,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=600,
    retry_jitter=True,
)
def verify_audit_chain_full(self):
    """Weekly full audit chain verification."""
    from app.services.audit import verify_chain as _verify
    logger.info("Starting full audit chain verification")
    result = asyncio.run(_run(_verify))
    logger.info("Full audit chain verification complete: %s", result)
    return result


@celery_app.task(
    bind=True,
    name="compliance.verify_backups",
    soft_time_limit=300,
    max_retries=3,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=600,
    retry_jitter=True,
)
def verify_backups(self):
    """Weekly backup integrity audit."""
    from app.services.compliance.backup_audit import verify_backups as _verify
    logger.info("Verifying backups")
    result = asyncio.run(_run(_verify))
    logger.info("Backup verification complete: %s", result)
    return result
