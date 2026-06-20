"""Event publisher — Redis Streams (dev) or Kafka/Redpanda (prod)."""

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from app.config import settings

logger = logging.getLogger(__name__)


class EventPublisher:
    """Publish events to Redis Streams or Kafka."""

    def __init__(self):
        self._backend = settings.event_backend if hasattr(settings, 'event_backend') else "redis"
        self._redis = None
        self._kafka_producer = None

        if self._backend == "redis":
            self._init_redis()
        elif self._backend == "kafka":
            self._init_kafka()

    def _init_redis(self):
        try:
            import redis.asyncio as aioredis
            self._redis = aioredis.from_url(settings.redis_url, decode_responses=True)
        except Exception as exc:
            logger.warning("Redis unavailable for event publishing: %s", exc)

    def _init_kafka(self):
        try:
            from kafka import KafkaProducer
            self._kafka_producer = KafkaProducer(
                bootstrap_servers=settings.kafka_bootstrap_servers,
                value_serializer=lambda v: json.dumps(v).encode(),
            )
        except Exception as exc:
            logger.warning("Kafka unavailable for event publishing: %s", exc)

    async def publish(self, topic: str, event_type: str, payload: Dict[str, Any]) -> bool:
        """Publish an event to the configured backend."""
        event = {
            "event_id": str(uuid.uuid4()),
            "event_type": event_type,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "payload": payload,
        }

        if self._backend == "redis" and self._redis:
            return await self._publish_redis(topic, event)
        elif self._backend == "kafka" and self._kafka_producer:
            return self._publish_kafka(topic, event)
        else:
            logger.debug("Event published (no backend): %s:%s", topic, event_type)
            return True

    async def _publish_redis(self, topic: str, event: Dict) -> bool:
        try:
            await self._redis.xadd(topic, {"data": json.dumps(event)}, maxlen=10000)
            return True
        except Exception as exc:
            logger.error("Redis publish failed: %s", exc)
            return False

    def _publish_kafka(self, topic: str, event: Dict) -> bool:
        try:
            self._kafka_producer.send(topic, value=event)
            return True
        except Exception as exc:
            logger.error("Kafka publish failed: %s", exc)
            return False


# Singleton
_publisher: Optional[EventPublisher] = None


def get_event_publisher() -> EventPublisher:
    global _publisher
    if _publisher is None:
        _publisher = EventPublisher()
    return _publisher
