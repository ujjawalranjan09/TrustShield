from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime

Base = declarative_base()

class FraudSession(Base):
    __tablename__ = "fraud_sessions"
    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String, unique=True, index=True)
    risk_score = Column(Integer)
    risk_level = Column(String)
    action_taken = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)

class RiskEvent(Base):
    __tablename__ = "risk_events"
    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String, ForeignKey("fraud_sessions.session_id"))
    event_type = Column(String)
    details = Column(String)
    timestamp = Column(DateTime, default=datetime.utcnow)
