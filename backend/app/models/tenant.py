"""Tenant model for multi-tenancy support."""

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import Boolean, Column, DateTime, String

from app.database import Base


class Tenant(Base):
    __tablename__ = "tenants"

    tenant_id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    slug = Column(String(100), unique=True, nullable=False, index=True)
    display_name = Column(String(200), nullable=False)
    tier = Column(String(20), nullable=False, default="bank")  # bank|enterprise|platform
    status = Column(String(20), nullable=False, default="active")  # active|suspended|offboarding
    data_region = Column(String(20), nullable=False, default="ap-south-1")
    is_sandbox = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
