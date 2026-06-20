"""User model with role-based access control."""

from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String

from app.database import Base
from app.models.tenant import Tenant  # noqa: F401 — ensures tenants table is registered in metadata before User mapper is configured


class User(Base):
    """Application user with role-based access."""

    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(String(36), ForeignKey("tenants.tenant_id"), nullable=True, index=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    full_name = Column(String(200), nullable=False)
    role = Column(String(20), default="analyst", nullable=False)  # super_admin, org_admin, analyst, viewer, bank
    org_name = Column(String(200))
    is_active = Column(Boolean, default=True, nullable=False)
    sso_subject = Column(String(255), nullable=True, index=True)
    idp_type = Column(String(20), nullable=True)  # saml | oidc
    token_version = Column(Integer, default=1, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
