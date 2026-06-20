"""Change management — records deployments and version changes."""

import logging
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Integer, String, Text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import Base

logger = logging.getLogger(__name__)


class ChangeRecord(Base):
    """Immutable record of platform deployments."""

    __tablename__ = "change_records"

    id = Column(Integer, primary_key=True, index=True)
    version = Column(String(50), nullable=False)
    git_sha = Column(String(40), nullable=False)
    deployer = Column(String(200), nullable=False)
    summary = Column(Text, nullable=False)
    affected_tenants = Column(Text, nullable=True)  # JSON array of tenant_ids
    risk_level = Column(String(20), nullable=False, default="low")  # low|medium|high|critical
    sunset_date = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


async def record_deploy(
    version: str,
    git_sha: str,
    deployer: str,
    summary: str,
    db: AsyncSession,
    affected_tenants: str | None = None,
    risk_level: str = "low",
    sunset_date: datetime | None = None,
) -> ChangeRecord:
    """Create a ChangeRecord for a deployment."""
    record = ChangeRecord(
        version=version,
        git_sha=git_sha,
        deployer=deployer,
        summary=summary,
        affected_tenants=affected_tenants,
        risk_level=risk_level,
        sunset_date=sunset_date,
    )
    db.add(record)
    await db.commit()
    await db.refresh(record)
    return record
