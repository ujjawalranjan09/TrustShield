"""Tests for the SLA Engine."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from app.services.governance.sla import compute_sla_attainment


@pytest.mark.asyncio
async def test_compute_sla_returns_correct_shape():
    """SLA computation must return a dict with uptime_pct, latency_p95_ms, audit_clean, overall_met."""
    mock_db = AsyncMock()

    # Mock total scans count
    total_result = MagicMock()
    total_result.scalar.return_value = 100
    # Mock successful scans count
    success_result = MagicMock()
    success_result.scalar.return_value = 98
    # Mock latency query
    latency_result = MagicMock()
    latency_result.all.return_value = [(100,), (150,), (200,), (250,), (300,)]
    # Mock audit logs
    audit_result = MagicMock()
    audit_result.scalars.return_value.all.return_value = []

    mock_db.execute = AsyncMock(side_effect=[total_result, success_result, latency_result, audit_result])

    result = await compute_sla_attainment("tenant-1", 6, 2026, mock_db)

    assert isinstance(result, dict)
    assert "uptime_pct" in result
    assert "latency_p95_ms" in result
    assert "audit_clean" in result
    assert "overall_met" in result
    assert result["uptime_pct"] == 98.0
    assert result["audit_clean"] is True


@pytest.mark.asyncio
async def test_audit_break_flags_breach():
    """Broken audit chain must set audit_clean=False and overall_met=False."""
    mock_db = AsyncMock()

    # Mock total scans count
    total_result = MagicMock()
    total_result.scalar.return_value = 50
    # Mock successful scans count
    success_result = MagicMock()
    success_result.scalar.return_value = 50
    # Mock latency query
    latency_result = MagicMock()
    latency_result.all.return_value = [(100,), (200,)]
    # Mock audit logs with broken chain
    log1 = MagicMock()
    log1.prev_hash = None
    log1.entry_hash = "hash_a"
    log2 = MagicMock()
    log2.prev_hash = "hash_wrong"  # Doesn't match log1's entry_hash
    log2.entry_hash = "hash_b"
    audit_result = MagicMock()
    audit_result.scalars.return_value.all.return_value = [log1, log2]

    mock_db.execute = AsyncMock(side_effect=[total_result, success_result, latency_result, audit_result])

    result = await compute_sla_attainment("tenant-1", 6, 2026, mock_db)

    assert result["audit_clean"] is False
    assert result["overall_met"] is False
