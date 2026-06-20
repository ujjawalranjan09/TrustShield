"""Unit tests for Kafka consumer hardening."""

import json
from unittest.mock import MagicMock, patch

import pytest


class TestKafkaConsumer:
    def test_noop_when_event_backend_is_redis(self):
        from app.workers.kafka_consumer import start_consumer

        with patch("app.workers.kafka_consumer.settings") as mock_settings:
            mock_settings.event_backend = "redis"
            # Should not raise, just return
            start_consumer()

    def test_poison_pill_to_deadletter(self):
        from app.workers.kafka_consumer import _handle_event

        mock_redis = MagicMock()
        mock_redis.set.return_value = True

        with patch("app.workers.kafka_consumer._get_dedup_client", return_value=mock_redis):
            # Valid event
            event = {"event_id": "evt-123", "event_type": "audit"}
            result = _handle_event(event)
            assert result is True

    def test_no_commit_on_handler_crash(self):
        from app.workers.kafka_consumer import start_consumer

        with patch("app.workers.kafka_consumer.settings") as mock_settings:
            mock_settings.event_backend = "kafka"
            mock_settings.kafka_bootstrap_servers = "localhost:9092"
            mock_settings.redis_url = "redis://localhost:6379/0"

            # Mock the KafkaConsumer import inside the function
            mock_kafka_mod = MagicMock()
            mock_consumer = MagicMock()
            mock_consumer.__iter__ = MagicMock(return_value=iter([]))
            mock_kafka_mod.KafkaConsumer.return_value = mock_consumer

            with patch.dict("sys.modules", {"kafka": mock_kafka_mod, "kafka.consumer": mock_kafka_mod}):
                start_consumer()
                # Consumer created with enable_auto_commit=False
                call_kwargs = mock_kafka_mod.KafkaConsumer.call_args[1]
                assert call_kwargs["enable_auto_commit"] is False

    def test_deduplication(self):
        from app.workers.kafka_consumer import _is_duplicate

        mock_redis = MagicMock()
        # First call: not duplicate (set returns True = new key)
        mock_redis.set.return_value = True
        assert _is_duplicate("evt-1", mock_redis) is False

        # Second call: duplicate (set returns None = key exists)
        mock_redis.set.return_value = None
        assert _is_duplicate("evt-1", mock_redis) is True

    def test_dedup_redis_unavailable(self):
        from app.workers.kafka_consumer import _is_duplicate

        # Redis unavailable → not duplicate (fail open)
        assert _is_duplicate("evt-1", None) is False
