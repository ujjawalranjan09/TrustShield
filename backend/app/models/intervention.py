"""Intervention log model — tracks coached-victim interventions."""

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.sql import func

from app.database import Base


class InterventionLog(Base):
    __tablename__ = "intervention_logs"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(String(36), ForeignKey("tenants.tenant_id"), nullable=True, index=True)
    session_id = Column(String(100), nullable=False, index=True)
    intervention_type = Column(String(50), nullable=False)  # cool_off, callback_request
    status = Column(String(20), default="triggered")  # triggered, acknowledged, completed, expired
    details = Column(Text, nullable=True)
    triggered_at = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
