"""Scan event model for tracking all analysis requests."""

from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String, UniqueConstraint

from app.database import Base


class ScanEvent(Base):
    """Records every scan/analysis request for dashboard metrics."""

    __tablename__ = "scan_events"

    __table_args__ = (
        UniqueConstraint("tenant_id", "session_id", name="uq_scan_events_tenant_session"),
    )

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(String(36), ForeignKey("tenants.tenant_id"), nullable=True, index=True)
    session_id = Column(String(100), index=True)
    scan_type = Column(String(20), nullable=False)  # analyze, scan-message, webhook, voice
    risk_score = Column(Integer)
    risk_level = Column(String(20))
    action_taken = Column(String(30))
    entities_found = Column(Integer, default=0)
    processing_time_ms = Column(Integer)
    client_ip = Column(String(45))
    model_confidence = Column(Float, nullable=True)  # B2.5 — model confidence score for drift monitoring
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
