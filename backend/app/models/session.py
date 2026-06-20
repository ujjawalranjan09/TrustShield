"""Revoked session model for token revocation."""

from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String

from app.database import Base


class RevokedSession(Base):
    """Revoked JWT session (access or refresh token)."""

    __tablename__ = "revoked_sessions"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(String(36), ForeignKey("tenants.tenant_id"), nullable=True, index=True)
    user_id = Column(Integer, index=True, nullable=False)
    token_jti = Column(String(36), unique=True, index=True, nullable=False)
    token_type = Column(String(20), nullable=False)  # "access" or "refresh"
    revoked_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
