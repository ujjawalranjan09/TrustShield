"""Drift monitoring log table — slim columns only."""

from sqlalchemy import JSON, Boolean, Column, DateTime, Float, Integer, String
from sqlalchemy.sql import func

from app.database import Base


class DriftLog(Base):
    __tablename__ = "drift_log"

    id = Column(Integer, primary_key=True, index=True)
    model_version = Column(String(50), nullable=False, index=True)
    feature_name = Column(String(100), nullable=False, index=True)
    psi_value = Column(Float, nullable=False)
    alert_triggered = Column(Boolean, default=False)
    reference_distribution = Column(JSON, nullable=True)
    run_id = Column(String(36), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
