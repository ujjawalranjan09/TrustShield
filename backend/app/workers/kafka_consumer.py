"""Kafka consumer for audit trail events.

Listens to the trustshield_events topic and logs audit events.
In production, events are forwarded to Elasticsearch/Logstash for the
ELK audit trail pipeline.
"""

import json
import logging

from kafka import KafkaConsumer

logger = logging.getLogger(__name__)

KAFKA_TOPIC = "trustshield_events"
KAFKA_BOOTSTRAP_SERVERS = ["kafka:9092"]
CONSUMER_GROUP = "trustshield-audit-group"


def start_consumer() -> None:
    """Start the Kafka consumer and process audit events."""
    try:
        consumer = KafkaConsumer(
            KAFKA_TOPIC,
            bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
            auto_offset_reset="earliest",
            enable_auto_commit=True,
            group_id=CONSUMER_GROUP,
            value_deserializer=lambda m: json.loads(m.decode("utf-8")),
        )

        logger.info("Kafka consumer started listening to %s", KAFKA_TOPIC)

        for message in consumer:
            logger.info("Received audit event: %s", message.value)
            # Insert into Elasticsearch/Logstash for ELK audit trail

    except Exception as e:
        logger.error("Kafka consumer error: %s", e)


if __name__ == "__main__":
    start_consumer()
