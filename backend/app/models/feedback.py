"""Feedback model for analyst labeling of fraud predictions."""

from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text

from app.database import Base


class FeedbackLabel(Base):
    """Analyst feedback on a fraud prediction for model improvement."""

    __tablename__ = "feedback_labels"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(String(36), ForeignKey("tenants.tenant_id"), nullable=True, index=True)
    session_id = Column(String(100), index=True, nullable=False)
    original_risk_score = Column(Integer)
    original_risk_level = Column(String(20))
    original_action = Column(String(30))
    analyst_label = Column(String(20), nullable=False)  # true_positive, false_positive, false_negative
    notes = Column(Text)
    analyst_email = Column(String(255))
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
