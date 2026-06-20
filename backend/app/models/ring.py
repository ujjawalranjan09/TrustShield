"""Fraud ring model — detected by community detection on the entity graph."""

from sqlalchemy import Column, DateTime, Integer, String
from sqlalchemy.sql import func

from app.database import Base


class FraudRing(Base):
    __tablename__ = "fraud_rings"

    id = Column(Integer, primary_key=True, index=True)
    ring_id = Column(String(36), unique=True, index=True, nullable=False)
    entity_count = Column(Integer, default=0)
    total_reports = Column(Integer, default=0)
    top_scam_type = Column(String(100))
    risk_level = Column(String(20), default="low")
    avg_pagerank = Column(Integer, default=0)
    status = Column(String(20), default="new")  # new, investigating, confirmed, dismissed
    detected_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
