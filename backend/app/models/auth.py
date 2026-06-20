"""Auth models for role-based access control."""

from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text

from app.database import Base


class Role(Base):
    __tablename__ = "roles"

    role_id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(String(36), nullable=True, index=True)
    name = Column(String(50), nullable=False)
    permissions = Column(Text, nullable=False, default="[]")  # JSON list of permission strings
    is_builtin = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class UserRole(Base):
    __tablename__ = "user_roles"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=False, index=True)
    role_id = Column(Integer, nullable=False, index=True)
    tenant_id = Column(String(36), nullable=True, index=True)
    assigned_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
