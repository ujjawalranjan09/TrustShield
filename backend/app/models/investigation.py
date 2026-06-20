"""Investigation case model — analyst-facing, NOT victim-facing recovery."""

from sqlalchemy import Column, DateTime, Integer, String, Text
from sqlalchemy.sql import func

from app.database import Base


class InvestigationCase(Base):
    __tablename__ = "investigation_cases"

    id = Column(Integer, primary_key=True, index=True)
    case_id = Column(String(36), unique=True, index=True, nullable=False)
    ring_id = Column(String(36), index=True, nullable=True)
    source = Column(String(20), default="ring_detection")  # ring_detection, manual, alert
    assigned_analyst_id = Column(Integer, nullable=True)
    status = Column(String(20), default="open")  # open, in_progress, closed, escalated
    priority = Column(String(20), default="high")  # low, medium, high, critical
    summary = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
