"""Idempotency helpers for Celery tasks.

Uses Redis SET NX with TTL to ensure each scheduled task runs at most once
per time bucket.
"""

import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


def _get_redis():
    """Get a Redis connection for deduplication."""
    try:
        import redis
        from app.config import settings
        return redis.from_url(settings.redis_url, decode_responses=True)
    except Exception as exc:
        logger.error("Failed to connect to Redis for idempotency: %s", exc)
        return None


def compute_task_id(task_name: str, bucket_format: str = "%Y%m%d%H") -> str:
    """Compute a deduplication key for a scheduled task.

    Args:
        task_name: The Celery task name.
        bucket_format: strftime format for the time bucket.
            Use "%Y%m%d%H" for hourly tasks, "%Y%m%d" for daily tasks.
    """
    bucket = datetime.now(timezone.utc).strftime(bucket_format)
    return f"{task_name}:{bucket}"


def try_acquire(task_id: str, ttl: int = 7200) -> bool:
    """Try to acquire a lock for this task run.

    Returns True if this is the first execution in the bucket (lock acquired).
    Returns False if another execution already completed or is running.
    """
    redis_client = _get_redis()
    if redis_client is None:
        # If Redis is unavailable, allow execution (fail open)
        return True

    try:
        result = redis_client.set(task_id, "running", nx=True, ex=ttl)
        return result is not None
    except Exception as exc:
        logger.error("Idempotency check failed for %s: %s", task_id, exc)
        return True  # Fail open


def mark_done(task_id: str) -> None:
    """Mark a task as successfully completed."""
    redis_client = _get_redis()
    if redis_client is None:
        return

    try:
        redis_client.set(task_id, "done")
    except Exception as exc:
        logger.error("Failed to mark task done: %s", exc)


def mark_failed(task_id: str) -> None:
    """Mark a task as failed."""
    redis_client = _get_redis()
    if redis_client is None:
        return

    try:
        redis_client.set(task_id, "failed")
    except Exception as exc:
        logger.error("Failed to mark task failed: %s", exc)
