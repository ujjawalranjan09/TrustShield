"""Unit tests for task idempotency and dead-letter queue."""

import pytest
from unittest.mock import MagicMock, patch


class TestIdempotency:
    def test_compute_task_id_hourly(self):
        from app.workers.idempotency import compute_task_id

        task_id = compute_task_id("billing.nightly_rollup", "%Y%m%d%H")
        assert task_id.startswith("billing.nightly_rollup:")
        # Should contain date and hour
        parts = task_id.split(":")
        assert len(parts) == 2
        assert len(parts[1]) == 10  # YYYYMMDDHH

    def test_compute_task_id_daily(self):
        from app.workers.idempotency import compute_task_id

        task_id = compute_task_id("billing.purge_old_usage_events", "%Y%m%d")
        assert task_id.startswith("billing.purge_old_usage_events:")
        parts = task_id.split(":")
        assert len(parts[1]) == 8  # YYYYMMDD

    def test_try_acquire_with_mock_redis(self):
        from app.workers.idempotency import try_acquire

        mock_redis = MagicMock()
        mock_redis.set.return_value = "OK"  # NX succeeded

        with patch("app.workers.idempotency._get_redis", return_value=mock_redis):
            result = try_acquire("test:task:20260101")
            assert result is True
            mock_redis.set.assert_called_once_with("test:task:20260101", "running", nx=True, ex=7200)

    def test_try_acquire_already_running(self):
        from app.workers.idempotency import try_acquire

        mock_redis = MagicMock()
        mock_redis.set.return_value = None  # NX failed — already exists

        with patch("app.workers.idempotency._get_redis", return_value=mock_redis):
            result = try_acquire("test:task:20260101")
            assert result is False

    def test_try_acquire_redis_unavailable_fails_open(self):
        from app.workers.idempotency import try_acquire

        with patch("app.workers.idempotency._get_redis", return_value=None):
            result = try_acquire("test:task:20260101")
            assert result is True  # Fail open

    def test_mark_done(self):
        from app.workers.idempotency import mark_done

        mock_redis = MagicMock()
        with patch("app.workers.idempotency._get_redis", return_value=mock_redis):
            mark_done("test:task:20260101")
            mock_redis.set.assert_called_once_with("test:task:20260101", "done")


class TestDeadLetter:
    def test_publish_to_queue(self):
        from app.workers.deadletter import DeadLetterPublisher

        mock_redis = MagicMock()
        publisher = DeadLetterPublisher(redis_client=mock_redis)

        publisher.publish(
            task_name="billing.nightly_rollup",
            payload={"date": "2026-01-01"},
            exc=RuntimeError("timeout"),
        )
        mock_redis.lpush.assert_called_once()
        call_args = mock_redis.lpush.call_args
        assert "trustshield-deadletter" in call_args[0]

    def test_depth_returns_count(self):
        from app.workers.deadletter import DeadLetterPublisher

        mock_redis = MagicMock()
        mock_redis.llen.return_value = 3
        publisher = DeadLetterPublisher(redis_client=mock_redis)

        depth = publisher.depth()
        assert depth == 3

    def test_depth_redis_unavailable(self):
        from app.workers.deadletter import DeadLetterPublisher

        publisher = DeadLetterPublisher(redis_client=None)
        # When _get_redis is also patched to return None
        with patch.object(publisher, "_get_redis", return_value=None):
            depth = publisher.depth()
            assert depth == 0
