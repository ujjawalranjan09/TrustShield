from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey
from datetime import datetime, timezone
from app.database import Base


class FraudSession(Base):
    """Records each analyzed chat session with its risk assessment outcome."""

    __tablename__ = "fraud_sessions"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String, unique=True, index=True)
    risk_score = Column(Integer)
    risk_level = Column(String)
    action_taken = Column(String)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class RiskEvent(Base):
    """Individual risk events logged during session analysis for audit trails."""

    __tablename__ = "risk_events"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String, ForeignKey("fraud_sessions.session_id"), index=True)
    event_type = Column(String)
    details = Column(String)
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc))
