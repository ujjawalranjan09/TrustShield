"""Recovery case model for victim assistance workflow."""

from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String, Text

from app.database import Base


class RecoveryCase(Base):
    """A fraud recovery case tracking victim assistance steps."""

    __tablename__ = "recovery_cases"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(String(36), ForeignKey("tenants.tenant_id"), nullable=True, index=True)
    case_id = Column(String(36), unique=True, index=True, nullable=False)
    fraud_type = Column(String(50), nullable=False)
    amount_lost = Column(Float, nullable=False)
    scammer_info = Column(Text)
    incident_date = Column(String(20), nullable=False)
    victim_name = Column(String(200))
    victim_phone = Column(String(15))
    bank_name = Column(String(200))
    upi_id = Column(String(255))
    current_step = Column(Integer, default=1)
    total_steps = Column(Integer, default=6)
    status = Column(String(20), default="in_progress")  # in_progress, completed, escalated
    # Cybercrime/1930 submission receipt fields (B3.3)
    cybercrime_ref_number = Column(String(50), nullable=True)
    cybercrime_submitted_at = Column(DateTime, nullable=True)
    cybercrime_submission_receipt = Column(Text, nullable=True)
    cybercrime_status = Column(String(20), default="not_submitted")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    last_updated = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
