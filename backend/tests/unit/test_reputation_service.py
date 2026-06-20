"""Tests for the enriched reputation service (D5.1)."""

import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.intel.reputation_service import (
    compute_reputation,
    get_public_reputation,
    _recency_weight,
    _tier,
    _mask_entity,
)


class TestRecencyWeight:
    def test_recent_report_full_weight(self):
        last_seen = datetime.now(timezone.utc) - timedelta(days=3)
        assert _recency_weight(last_seen) == 1.0

    def test_old_report_low_weight(self):
        last_seen = datetime.now(timezone.utc) - timedelta(days=200)
        assert _recency_weight(last_seen) == 0.1

    def test_none_returns_low_weight(self):
        assert _recency_weight(None) == 0.1

    def test_boundary_30_days(self):
        last_seen = datetime.now(timezone.utc) - timedelta(days=30)
        assert _recency_weight(last_seen) == 0.7

    def test_boundary_90_days(self):
        last_seen = datetime.now(timezone.utc) - timedelta(days=90)
        assert _recency_weight(last_seen) == 0.4


class TestTier:
    def test_confirmed_scam(self):
        assert _tier(80) == "confirmed_scam"
        assert _tier(100) == "confirmed_scam"

    def test_suspicious(self):
        assert _tier(50) == "suspicious"
        assert _tier(79) == "suspicious"

    def test_watch(self):
        assert _tier(20) == "watch"
        assert _tier(49) == "watch"

    def test_clean(self):
        assert _tier(0) == "clean"
        assert _tier(19) == "clean"


class TestMaskEntity:
    def test_short_entity(self):
        assert _mask_entity("ab") == "a***"

    def test_long_entity(self):
        assert _mask_entity("user@paytm") == "use***tm"


class TestReputationService:
    @pytest.mark.asyncio
    async def test_reputation_rises_with_recent_reports(self):
        """More recent reports should yield higher score."""
        db = AsyncMock()
        entity_recent = MagicMock()
        entity_recent.report_count = 20
        entity_recent.last_seen = datetime.now(timezone.utc) - timedelta(days=2)
        entity_recent.first_reported = datetime.now(timezone.utc) - timedelta(days=10)
        entity_recent.scam_type = "upi_scam"

        entity_old = MagicMock()
        entity_old.report_count = 20
        entity_old.last_seen = datetime.now(timezone.utc) - timedelta(days=150)
        entity_old.first_reported = datetime.now(timezone.utc) - timedelta(days=200)
        entity_old.scam_type = "upi_scam"

        mock_result_recent = MagicMock()
        mock_result_recent.scalars.return_value.first.return_value = entity_recent
        mock_result_old = MagicMock()
        mock_result_old.scalars.return_value.first.return_value = entity_old

        mock_cross = MagicMock()
        mock_cross.scalars.return_value.first.return_value = None

        with patch("app.services.intel.reputation_service._get_propagated_risk", new_callable=AsyncMock, return_value=0.0), \
             patch("app.services.intel.reputation_service._get_ring_info", new_callable=AsyncMock, return_value={"ring_id": None, "ring_status": None, "ring_risk": None}):
            call_count = [0]
            async def mock_execute(stmt, **kwargs):
                call_count[0] += 1
                if call_count[0] <= 1:
                    return mock_result_recent
                return mock_cross

            db.execute = mock_execute
            recent_result = await compute_reputation("test@upi", "UPI", db)

            call_count[0] = 0
            async def mock_execute2(stmt, **kwargs):
                call_count[0] += 1
                if call_count[0] <= 1:
                    return mock_result_old
                return mock_cross

            db.execute = mock_execute2
            old_result = await compute_reputation("test@upi", "UPI", db)

        assert recent_result["score"] > old_result["score"]

    @pytest.mark.asyncio
    async def test_reputation_decays_with_age(self):
        """Older reports should produce lower scores than recent ones."""
        db = AsyncMock()

        entity_new = MagicMock()
        entity_new.report_count = 5
        entity_new.last_seen = datetime.now(timezone.utc) - timedelta(days=5)
        entity_new.first_reported = datetime.now(timezone.utc) - timedelta(days=20)

        entity_aged = MagicMock()
        entity_aged.report_count = 5
        entity_aged.last_seen = datetime.now(timezone.utc) - timedelta(days=100)
        entity_aged.first_reported = datetime.now(timezone.utc) - timedelta(days=120)

        mock_cross = MagicMock()
        mock_cross.scalars.return_value.first.return_value = None

        with patch("app.services.intel.reputation_service._get_propagated_risk", new_callable=AsyncMock, return_value=0.0), \
             patch("app.services.intel.reputation_service._get_ring_info", new_callable=AsyncMock, return_value={"ring_id": None, "ring_status": None, "ring_risk": None}):
            call_count = [0]
            async def mock_execute(stmt, **kwargs):
                call_count[0] += 1
                if call_count[0] <= 1:
                    r = MagicMock()
                    r.scalars.return_value.first.return_value = entity_new
                    return r
                return mock_cross

            db.execute = mock_execute
            new_result = await compute_reputation("test@upi", "UPI", db)

            call_count[0] = 0
            async def mock_execute2(stmt, **kwargs):
                call_count[0] += 1
                if call_count[0] <= 1:
                    r = MagicMock()
                    r.scalars.return_value.first.return_value = entity_aged
                    return r
                return mock_cross

            db.execute = mock_execute2
            aged_result = await compute_reputation("test@upi", "UPI", db)

        assert new_result["score"] > aged_result["score"]

    @pytest.mark.asyncio
    async def test_ring_membership_bumps_tier(self):
        """Entity in a confirmed ring should score higher."""
        db = AsyncMock()
        entity = MagicMock()
        entity.report_count = 5
        entity.last_seen = datetime.now(timezone.utc) - timedelta(days=5)
        entity.first_reported = datetime.now(timezone.utc) - timedelta(days=20)

        mock_cross = MagicMock()
        mock_cross.scalars.return_value.first.return_value = None

        with patch("app.services.intel.reputation_service._get_propagated_risk", new_callable=AsyncMock, return_value=0.0), \
             patch("app.services.intel.reputation_service._get_ring_info", new_callable=AsyncMock, return_value={"ring_id": "ring-abc", "ring_status": "confirmed", "ring_risk": "critical"}):
            call_count = [0]
            async def mock_execute(stmt, **kwargs):
                call_count[0] += 1
                if call_count[0] <= 1:
                    r = MagicMock()
                    r.scalars.return_value.first.return_value = entity
                    return r
                return mock_cross

            db.execute = mock_execute
            ring_result = await compute_reputation("test@upi", "UPI", db)

        with patch("app.services.intel.reputation_service._get_propagated_risk", new_callable=AsyncMock, return_value=0.0), \
             patch("app.services.intel.reputation_service._get_ring_info", new_callable=AsyncMock, return_value={"ring_id": None, "ring_status": None, "ring_risk": None}):
            call_count[0] = 0
            async def mock_execute2(stmt, **kwargs):
                call_count[0] += 1
                if call_count[0] <= 1:
                    r = MagicMock()
                    r.scalars.return_value.first.return_value = entity
                    return r
                return mock_cross

            db.execute = mock_execute2
            no_ring_result = await compute_reputation("test@upi", "UPI", db)

        assert ring_result["score"] > no_ring_result["score"]
        assert ring_result["ring_membership"] == "ring-abc"

    @pytest.mark.asyncio
    async def test_cross_bank_corroboration_weights_higher(self):
        """More banks reporting should increase the score."""
        db = AsyncMock()
        entity = MagicMock()
        entity.report_count = 5
        entity.last_seen = datetime.now(timezone.utc) - timedelta(days=5)
        entity.first_reported = datetime.now(timezone.utc) - timedelta(days=20)

        cross_many = MagicMock()
        cross_many.banks_reporting = 4
        cross_many.total_reports = 12

        cross_none = MagicMock()
        cross_none.banks_reporting = 0
        cross_none.total_reports = 0

        with patch("app.services.intel.reputation_service._get_propagated_risk", new_callable=AsyncMock, return_value=0.0), \
             patch("app.services.intel.reputation_service._get_ring_info", new_callable=AsyncMock, return_value={"ring_id": None, "ring_status": None, "ring_risk": None}):
            call_count = [0]
            async def mock_execute(stmt, **kwargs):
                call_count[0] += 1
                if call_count[0] <= 1:
                    r = MagicMock()
                    r.scalars.return_value.first.return_value = entity
                    return r
                r = MagicMock()
                r.scalars.return_value.first.return_value = cross_many
                return r

            db.execute = mock_execute
            many_bank_result = await compute_reputation("test@upi", "UPI", db)

            call_count[0] = 0
            async def mock_execute2(stmt, **kwargs):
                call_count[0] += 1
                if call_count[0] <= 1:
                    r = MagicMock()
                    r.scalars.return_value.first.return_value = entity
                    return r
                r = MagicMock()
                r.scalars.return_value.first.return_value = cross_none
                return r

            db.execute = mock_execute2
            no_bank_result = await compute_reputation("test@upi", "UPI", db)

        assert many_bank_result["score"] > no_bank_result["score"]

    @pytest.mark.asyncio
    async def test_public_response_omits_detailed_fields(self):
        """Public endpoint should only return tier + count bucket, not raw fields."""
        db = AsyncMock()
        entity = MagicMock()
        entity.report_count = 5
        entity.last_seen = datetime.now(timezone.utc) - timedelta(days=5)
        entity.first_reported = datetime.now(timezone.utc) - timedelta(days=20)

        mock_cross = MagicMock()
        mock_cross.scalars.return_value.first.return_value = None

        with patch("app.services.intel.reputation_service._get_propagated_risk", new_callable=AsyncMock, return_value=0.0), \
             patch("app.services.intel.reputation_service._get_ring_info", new_callable=AsyncMock, return_value={"ring_id": None, "ring_status": None, "ring_risk": None}):
            call_count = [0]
            async def mock_execute(stmt, **kwargs):
                call_count[0] += 1
                if call_count[0] <= 1:
                    r = MagicMock()
                    r.scalars.return_value.first.return_value = entity
                    return r
                return mock_cross

            db.execute = mock_execute
            result = await get_public_reputation("test@upi", "UPI", db)

        assert "reputation_tier" in result
        assert "report_count_bucket" in result
        assert "score" in result
        assert "entity" in result
        assert "propagated_risk" not in result
        assert "ring_membership" not in result
        assert "last_reported_at" not in result
        assert "first_seen" not in result

    @pytest.mark.asyncio
    async def test_unknown_entity_returns_clean_tier(self):
        """Entity with no reports should return clean tier."""
        db = AsyncMock()
        mock_empty = MagicMock()
        mock_empty.scalars.return_value.first.return_value = None

        call_count = [0]
        async def mock_execute(stmt, **kwargs):
            call_count[0] += 1
            return mock_empty

        db.execute = mock_execute

        with patch("app.services.intel.reputation_service._get_propagated_risk", new_callable=AsyncMock, return_value=0.0), \
             patch("app.services.intel.reputation_service._get_ring_info", new_callable=AsyncMock, return_value={"ring_id": None, "ring_status": None, "ring_risk": None}):
            result = await compute_reputation("unknown@upi", "UPI", db)

        assert result["reputation_tier"] == "clean"
        assert result["score"] == 0
        assert result["direct_reports"] == 0
