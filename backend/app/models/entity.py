"""Entity report and flagged entity models.

EntityReport stores individual report submissions. FlaggedEntity tracks
the aggregated state of each reported entity (total reports, risk level).
"""

from sqlalchemy import Column, Float, Integer, String, DateTime, Text, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
from app.database import Base


class FlaggedEntity(Base):
    """Aggregated entity record — one row per unique entity value+type."""

    __tablename__ = "flagged_entities"

    id = Column(Integer, primary_key=True, index=True)
    entity_value = Column(String(255), unique=True, index=True, nullable=False)
    entity_type = Column(String(20), nullable=False)
    scam_type = Column(String(100))
    description = Column(Text)
    report_count = Column(Integer, default=1, nullable=False)
    is_confirmed = Column(Integer, default=0)
    first_reported = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    last_seen = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    source = Column(String(50), default="user_report")  # user_report, threat_intel, cross_bank

    # Geo columns (populated when available from reporter/device)
    region = Column(String(100), nullable=True)
    pincode = Column(String(10), nullable=True)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)

    reports = relationship(
        "EntityReport", back_populates="entity", cascade="all, delete-orphan"
    )


class EntityReport(Base):
    """Individual report submission for an entity."""

    __tablename__ = "entity_reports"

    id = Column(Integer, primary_key=True, index=True)
    report_id = Column(String(36), unique=True, index=True, nullable=False)
    entity_id = Column(Integer, ForeignKey("flagged_entities.id"), index=True)
    reporter_contact = Column(String(255))
    scam_type = Column(String(100))
    description = Column(Text)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    entity = relationship("FlaggedEntity", back_populates="reports")
