from sqlalchemy import Column, Integer, String, DateTime
from app.models.session import Base
from datetime import datetime

class FlaggedEntity(Base):
    __tablename__ = "flagged_entities"
    id = Column(Integer, primary_key=True, index=True)
    entity_value = Column(String, unique=True, index=True)
    entity_type = Column(String)
    report_count = Column(Integer, default=1)
    last_seen = Column(DateTime, default=datetime.utcnow)
