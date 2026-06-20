"""Data Asset model for DPDP data register (DPDP §8 compliance)."""

from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Integer, String, Text

from app.database import Base


class DataAsset(Base):
    """Machine-readable inventory of PII data assets — DPDP §8."""

    __tablename__ = "dpdp_data_register"

    id = Column(Integer, primary_key=True, index=True)
    asset_name = Column(String(200), nullable=False, unique=True)
    table_name = Column(String(100), nullable=False)
    column_names = Column(Text, nullable=False)  # JSON list
    pii_category = Column(String(50), nullable=False)  # contact|financial|identity|behavioral
    lawful_basis = Column(String(50), nullable=False)  # consent|legal_obligation|legitimate_interest
    retention_policy = Column(String(200), nullable=False)
    storage_location = Column(String(200), nullable=False)
    shared_with = Column(Text, nullable=True)  # JSON list
    last_reviewed = Column(DateTime, nullable=True)
    dpo_contact = Column(String(200), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))