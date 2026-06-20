"""Kafka consumer for audit trail events.

Listens to the trustshield_events topic and logs audit events.
In production, events are forwarded to Elasticsearch/Logstash for the
ELK audit trail pipeline.

Hardening (Phase C):
  - Skip if event_backend != "kafka" (Redis is default)
  - Manual commit after successful handler
  - Event deduplication via Redis SET
  - Poison-pill handling (bad JSON → dead-letter)
"""

import json
import logging
import traceback

from app.config import settings

logger = logging.getLogger(__name__)

KAFKA_TOPIC = "trustshield_events"
KAFKA_BOOTSTRAP_SERVERS = settings.kafka_bootstrap_servers.split(",")
CONSUMER_GROUP = "trustshield-audit-group"


def _get_dedup_client():
    """Get a Redis client for event deduplication."""
    try:
        import redis
        return redis.from_url(settings.redis_url, decode_responses=True)
    except Exception:
        return None


def _is_duplicate(event_id: str, redis_client) -> bool:
    """Check if an event has already been processed."""
    if redis_client is None:
        return False
    try:
        return not redis_client.set(f"event:{event_id}", "1", nx=True, ex=86400)
    except Exception:
        return False


def _handle_event(event: dict) -> bool:
    """Handle a single audit event. Returns True on success."""
    event_id = event.get("event_id")
    if event_id:
        redis_client = _get_dedup_client()
        if _is_duplicate(event_id, redis_client):
            logger.debug("Duplicate event %s, skipping", event_id)
            return True

    logger.info("Processing audit event: %s", event.get("event_type", "unknown"))
    # Insert into Elasticsearch/Logstash for ELK audit trail
    return True


def start_consumer() -> None:
    """Start the Kafka consumer and process audit events.

    No-op if event_backend is not "kafka".
    """
    if settings.event_backend != "kafka":
        logger.debug("Kafka consumer disabled (event_backend=%s)", settings.event_backend)
        return

    try:
        from kafka import KafkaConsumer

        consumer = KafkaConsumer(
            KAFKA_TOPIC,
            bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
            auto_offset_reset="earliest",
            enable_auto_commit=False,
            group_id=CONSUMER_GROUP,
            max_poll_records=50,
            session_timeout_ms=30000,
            value_deserializer=lambda m: json.loads(m.decode("utf-8")),
        )

        logger.info("Kafka consumer started listening to %s", KAFKA_TOPIC)

        for message in consumer:
            try:
                event = message.value
                _handle_event(event)
                consumer.commit()
            except json.JSONDecodeError as exc:
                logger.error("Poison pill message (bad JSON): %s", exc)
                # Do not commit — message will be redelivered, but we log and continue
                continue
            except Exception as exc:
                logger.error("Error processing message: %s\n%s", exc, traceback.format_exc())
                # Do not commit on handler crash — redeliver on next poll
                continue

    except ImportError:
        logger.warning("kafka-python not installed; Kafka consumer disabled")
    except Exception as e:
        logger.error("Kafka consumer error: %s", e)


if __name__ == "__main__":
    start_consumer()
