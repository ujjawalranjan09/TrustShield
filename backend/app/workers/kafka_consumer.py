import json
import logging
from kafka import KafkaConsumer

logging.basicConfig(level=logging.INFO)

def start_consumer():
    try:
        consumer = KafkaConsumer(
            'trustshield_events',
            bootstrap_servers=['kafka:9092'],
            auto_offset_reset='earliest',
            enable_auto_commit=True,
            group_id='trustshield-audit-group',
            value_deserializer=lambda m: json.loads(m.decode('utf-8'))
        )

        logging.info("Kafka consumer started listening to trustshield_events...")

        for message in consumer:
            logging.info(f"Received audit event: {message.value}")
            # Insert into Elasticsearch/Logstash for ELK audit trail

    except Exception as e:
        logging.error(f"Kafka consumer error: {e}")

if __name__ == "__main__":
    start_consumer()
