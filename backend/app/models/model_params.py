"""Model version configuration table."""

from sqlalchemy import Boolean, Column, DateTime, Float, Integer, String
from sqlalchemy.sql import func

from app.database import Base


class ModelParams(Base):
    __tablename__ = "model_params"

    id = Column(Integer, primary_key=True, index=True)
    model_version = Column(String(50), unique=True, nullable=False, index=True)
    transformer_weight = Column(Float, default=0.6)
    gbm_weight = Column(Float, default=0.4)
    ensemble_weights = Column(String(500), default="{}")
    feature_weights = Column(String(1000), default="{}")
    transformer_f1 = Column(Float, nullable=True)
    gbm_f1 = Column(Float, nullable=True)
    ensemble_f1 = Column(Float, nullable=True)
    gold_set_f1 = Column(Float, nullable=True)
    is_active = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    promoted_at = Column(DateTime(timezone=True), nullable=True)
