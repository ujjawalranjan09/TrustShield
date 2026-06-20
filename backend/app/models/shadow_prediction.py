"""Shadow prediction model for shadow-mode model evaluation."""

from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String

from app.database import Base


class ShadowPrediction(Base):
    """Record of a shadow-mode prediction for model comparison.

    Stores the primary (production) model's output alongside the shadow
    (candidate) model's output for the same input.
    """

    __tablename__ = "shadow_predictions"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(String(36), ForeignKey("tenants.tenant_id"), nullable=True, index=True)
    session_id = Column(String(100), index=True, nullable=False)
    primary_prediction = Column(Integer, nullable=False)
    primary_confidence = Column(Float, nullable=False)
    shadow_prediction = Column(Integer, nullable=False)
    shadow_confidence = Column(Float, nullable=False)
    shadow_model_version = Column(String(50), nullable=True)
    primary_model_version = Column(String(50), nullable=True)
    agreement = Column(Integer, nullable=False)  # 1 if same prediction, else 0
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))