"""Dead-letter queue for Celery tasks.

Handles tasks that have exhausted all retries.
"""

import json
import logging
import traceback
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)


class DeadLetterPublisher:
    """Publish failed tasks to a dead-letter queue."""

    def __init__(self, redis_client=None):
        self._redis = redis_client

    def _get_redis(self):
        if self._redis is not None:
            return self._redis
        try:
            import redis
            from app.config import settings
            self._redis = redis.from_url(settings.redis_url, decode_responses=True)
        except Exception as exc:
            logger.error("Failed to connect to Redis for dead-letter: %s", exc)
            return None
        return self._redis

    def publish(
        self,
        task_name: str,
        payload: dict,
        exc: Exception,
        tb: Optional[str] = None,
    ) -> None:
        """Push a failed task to the dead-letter queue."""
        from app.config import settings

        entry = {
            "task_name": task_name,
            "payload": payload,
            "error": str(exc),
            "traceback": tb or traceback.format_exc(),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        queue_name = settings.celery_deadletter_queue
        redis_client = self._get_redis()
        if redis_client is None:
            logger.error("Cannot publish to dead-letter: no Redis connection")
            return

        try:
            redis_client.lpush(queue_name, json.dumps(entry))
            logger.warning("Task %s dead-lettered to %s", task_name, queue_name)
        except Exception as exc:
            logger.error("Failed to publish to dead-letter queue: %s", exc)

    def depth(self, task_name: Optional[str] = None) -> int:
        """Return the current dead-letter queue depth."""
        from app.config import settings

        redis_client = self._get_redis()
        if redis_client is None:
            return 0

        queue_name = settings.celery_deadletter_queue
        try:
            return redis_client.llen(queue_name)
        except Exception:
            return 0


# Module-level singleton
publisher = DeadLetterPublisher()
