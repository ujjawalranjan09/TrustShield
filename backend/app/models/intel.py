"""Intel Network models for cross-bank fraud intelligence sharing."""

from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String, Text

from app.database import Base


class Bank(Base):
    """Registered bank/fintech partner in the intelligence network."""

    __tablename__ = "intel_banks"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(String(36), ForeignKey("tenants.tenant_id"), nullable=True, index=True)
    bank_id = Column(String(36), unique=True, index=True, nullable=False)
    bank_name = Column(String(200), nullable=False)
    bank_code = Column(String(20), unique=True, nullable=False)
    contact_email = Column(String(255), nullable=False)
    contact_name = Column(String(200), nullable=False)
    api_key_hash = Column(String(64), unique=True, nullable=False)
    freeze_webhook_url = Column(String(500), nullable=True)
    is_active = Column(Integer, default=1)
    registered_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class SharedEntity(Base):
    """Entity shared across the intelligence network (hashed values only)."""

    __tablename__ = "intel_shared_entities"

    id = Column(Integer, primary_key=True, index=True)
    entity_hash = Column(String(64), unique=True, index=True, nullable=False)
    entity_type = Column(String(20), nullable=False)
    total_reports = Column(Integer, default=0)
    banks_reporting = Column(Integer, default=0)
    cross_bank_risk_score = Column(Float, default=0.0)
    scam_types = Column(Text)  # JSON array as string
    first_shared = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    last_updated = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class CrossBankReport(Base):
    """Individual report from a bank about a shared entity."""

    __tablename__ = "intel_cross_bank_reports"

    id = Column(Integer, primary_key=True, index=True)
    entity_hash = Column(String(64), index=True, nullable=False)
    bank_id = Column(String(36), index=True, nullable=False)
    scam_type = Column(String(100), nullable=False)
    risk_score = Column(Integer)
    incident_count = Column(Integer, default=1)
    notes = Column(Text)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
