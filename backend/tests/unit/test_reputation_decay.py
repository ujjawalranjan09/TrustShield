"""Tests for reputation refresh and decay jobs (D5.3)."""

import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch


class TestReputationDecay:
    @pytest.mark.asyncio
    async def test_entity_old_reports_trends_clean(self):
        """Entities with very old reports should trend toward clean tier."""
        from app.services.intel.reputation_service import _recency_weight

        old_last_seen = datetime.now(timezone.utc) - timedelta(days=200)
        weight = _recency_weight(old_last_seen)
        assert weight == 0.1

        import math
        report_count = 3
        base_score = min(50, math.log(1 + report_count) * 10) * weight
        assert base_score < 20

    @pytest.mark.asyncio
    async def test_re_reported_entity_resets_decay(self):
        """An entity that is re-reported should have recent last_seen."""
        from app.services.intel.reputation_service import _recency_weight

        recent = datetime.now(timezone.utc) - timedelta(days=2)
        weight = _recency_weight(recent)
        assert weight == 1.0

    @pytest.mark.asyncio
    async def test_refresh_is_idempotent(self):
        """Running reputation_refresh twice should not fail."""
        from app.workers.tasks.reputation_tasks import _reputation_refresh

        mock_entity = MagicMock()
        mock_entity.entity_value = "UPI:test@upi"
        mock_entity.entity_type = "UPI"
        mock_entity.report_count = 5
        mock_entity.last_seen = datetime.now(timezone.utc) - timedelta(days=5)
        mock_entity.first_reported = datetime.now(timezone.utc) - timedelta(days=20)

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_entity]

        with patch("app.database.AsyncSessionLocal") as mock_session_cls, \
             patch("app.services.intel.reputation_service._get_propagated_risk", new_callable=AsyncMock, return_value=0.0), \
             patch("app.services.intel.reputation_service._get_ring_info", new_callable=AsyncMock, return_value={"ring_id": None, "ring_status": None, "ring_risk": None}):
            mock_session = AsyncMock()
            mock_session.execute.return_value = mock_result
            mock_session_cls.return_value.__aenter__.return_value = mock_session
            mock_session_cls.return_value.__aexit__.return_value = False

            result1 = await _reputation_refresh()
            result2 = await _reputation_refresh()

        assert result1["status"] == "success"
        assert result2["status"] == "success"
        assert result1["entities_refreshed"] == result2["entities_refreshed"]


class TestReputationConfig:
    def test_decay_days_default(self):
        from app.config import settings
        assert settings.reputation_decay_days == 180


class TestCeleryRegistration:
    def test_reputation_tasks_included(self):
        from app.workers.celery_app import celery_app
        assert "app.workers.tasks.reputation_tasks" in celery_app.conf.include

    def test_beat_schedule_has_refresh(self):
        from app.workers.celery_app import celery_app
        schedule = celery_app.conf.beat_schedule
        assert "reputation-refresh" in schedule

    def test_refresh_task_name(self):
        from app.workers.tasks.reputation_tasks import reputation_refresh
        assert reputation_refresh.name == "app.workers.tasks.reputation_tasks.reputation_refresh"
