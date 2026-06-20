"""Refresh token model for rotation and reuse detection."""

from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, Integer, String

from app.database import Base


class RefreshToken(Base):
    """Refresh token with family-based rotation and reuse detection."""

    __tablename__ = "refresh_tokens"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, index=True, nullable=False)
    token_jti = Column(String(36), unique=True, index=True, nullable=False)
    family_id = Column(String(36), index=True, nullable=False)
    is_rotated = Column(Boolean, default=False, nullable=False)
    is_revoked = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    rotated_at = Column(DateTime, nullable=True)
    revoked_at = Column(DateTime, nullable=True)
