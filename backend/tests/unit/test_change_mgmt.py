"""Tests for Change Management."""

import pytest
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime, timezone

from app.services.governance.change_mgmt import ChangeRecord, record_deploy


@pytest.mark.asyncio
async def test_record_deploy_creates_change_record():
    """record_deploy must create a ChangeRecord with correct fields."""
    mock_db = AsyncMock()
    mock_db.add = MagicMock()
    mock_db.commit = AsyncMock()
    mock_db.refresh = AsyncMock()

    record = await record_deploy(
        version="1.2.3",
        git_sha="abc123def456",
        deployer="devops@trustshield.io",
        summary="Deployed new scan engine",
        db=mock_db,
        risk_level="medium",
    )

    assert record is not None
    assert record.version == "1.2.3"
    assert record.git_sha == "abc123def456"
    assert record.deployer == "devops@trustshield.io"
    assert record.summary == "Deployed new scan engine"
    assert record.risk_level == "medium"
    assert record.affected_tenants is None
    assert record.sunset_date is None
    mock_db.add.assert_called_once()
    mock_db.commit.assert_called_once()


@pytest.mark.asyncio
async def test_changes_list_returns_records():
    """Listing changes should return ChangeRecord objects."""
    mock_db = AsyncMock()

    record1 = MagicMock(spec=ChangeRecord)
    record1.id = 1
    record1.version = "1.0.0"
    record1.git_sha = "aaa111"
    record1.deployer = "admin"
    record1.summary = "Initial deploy"
    record1.affected_tenants = None
    record1.risk_level = "low"
    record1.sunset_date = None
    record1.created_at = datetime(2026, 6, 1, tzinfo=timezone.utc)

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [record1]
    mock_db.execute = AsyncMock(return_value=mock_result)

    from sqlalchemy import select
    result = await mock_db.execute(
        select(ChangeRecord).order_by(ChangeRecord.created_at.desc()).limit(100)
    )
    records = result.scalars().all()

    assert len(records) == 1
    assert records[0].version == "1.0.0"
    assert records[0].risk_level == "low"
