"""Behavioral signals model — stores SDK telemetry for fraud detection."""

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.sql import func

from app.database import Base


class BehavioralSignal(Base):
    __tablename__ = "behavioral_signals"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(String(36), ForeignKey("tenants.tenant_id"), nullable=True, index=True)
    session_id = Column(String(100), nullable=False, index=True)
    signal_type = Column(String(50), nullable=False)
    value = Column(Float, nullable=False)
    device_fingerprint = Column(String(256), nullable=True)
    metadata_json = Column(Text, nullable=True)
    timestamp = Column(DateTime, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
