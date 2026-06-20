"""Authentication and authorization dependencies."""

import json
import logging
from typing import Set

from fastapi import Depends, HTTPException, Request, Security
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_async_db
from app.models.session import RevokedSession
from app.models.user import User
from app.services.auth.jwt_service import (
    TokenExpiredError,
    TokenMalformedError,
    decode_token,
)

logger = logging.getLogger(__name__)

# Legacy API key scheme
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

# JWT Bearer scheme (kept for API clients that pass Authorization header)
bearer_scheme = HTTPBearer(auto_error=False)


async def verify_api_key(api_key: str = Security(api_key_header)) -> bool:
    """Verify API key for protected endpoints (legacy, backward compat)."""
    if not settings.api_key:
        return True
    if not api_key:
        raise HTTPException(status_code=401, detail="Missing API key. Provide X-API-Key header.")
    if api_key != settings.api_key:
        raise HTTPException(status_code=403, detail="Invalid API key.")
    return True


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_async_db),
) -> User:
    """Extract and validate JWT token from cookie or Authorization header.

    Priority:
    1. httpOnly cookie `ts_access_token` (browser flow)
    2. Authorization: Bearer header (API clients, bank SDK)
    """
    token = None

    # 1. Try httpOnly cookie first
    cookie_token = request.cookies.get("ts_access_token")
    if cookie_token:
        token = cookie_token

    # 2. Fall back to Authorization header
    if not token and credentials:
        token = credentials.credentials

    if not token:
        raise HTTPException(status_code=401, detail="Missing authentication token")

    try:
        payload = decode_token(token)
    except TokenExpiredError:
        raise HTTPException(status_code=401, detail="Token has expired")
    except TokenMalformedError:
        raise HTTPException(status_code=401, detail="Malformed authentication token")

    if payload.get("type") != "access":
        raise HTTPException(status_code=401, detail="Expected access token")

    user_id = payload.get("sub")
    token_jti = payload.get("jti")

    if not user_id:
        raise HTTPException(status_code=401, detail="Token missing user ID")

    # Check if token has been revoked
    if token_jti:
        result = await db.execute(
            select(RevokedSession).filter(RevokedSession.token_jti == token_jti)
        )
        if result.scalars().first():
            raise HTTPException(status_code=401, detail="Token has been revoked")

    result = await db.execute(select(User).filter(User.id == int(user_id)))
    user = result.scalars().first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account is deactivated")

    # E2.5: Reject token if token_version has been incremented (e.g. SCIM deactivation)
    token_ver = payload.get("token_version", 1)
    user_ver = user.token_version or 1
    if token_ver != user_ver:
        raise HTTPException(status_code=401, detail="Token invalidated — session version mismatch")

    return user


async def _get_user_permissions(user: User, db: AsyncSession) -> Set[str]:
    """Collect all permissions for a user from their roles."""
    from app.models.auth import Role, UserRole
    from app.services.auth.permissions import get_permissions_for_role

    perms: Set[str] = get_permissions_for_role(user.role)

    result = await db.execute(
        select(UserRole).filter(UserRole.user_id == user.id)
    )
    for ur in result.scalars().all():
        role_result = await db.execute(
            select(Role).filter(Role.role_id == ur.role_id)
        )
        role = role_result.scalars().first()
        if role and role.permissions:
            try:
                perms.update(json.loads(role.permissions))
            except (json.JSONDecodeError, TypeError):
                pass
    return perms


def require_permission(*required_perms: str):
    """Dependency factory: reject if user lacks any of the required permissions."""

    async def _check(
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_async_db),
    ) -> User:
        perms = await _get_user_permissions(current_user, db)
        missing = set(required_perms) - perms
        if missing:
            raise HTTPException(
                status_code=403,
                detail=f"Missing permissions: {', '.join(sorted(missing))}",
            )
        return current_user

    return _check


def require_role(*allowed_roles: str):
    """Dependency factory: reject if current user's role is not in allowed_roles.

    Kept for backward compatibility — prefer require_permission for new code.
    """

    async def _check_role(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in allowed_roles:
            raise HTTPException(
                status_code=403,
                detail=f"Insufficient permissions. Required: {', '.join(allowed_roles)}",
            )
        return current_user

    return _check_role
