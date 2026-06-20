"""Authentication endpoints: register, login, refresh, logout, me."""

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_async_db
from app.models.refresh_token import RefreshToken
from app.models.session import RevokedSession
from app.models.user import User
from app.services.auth.jwt_service import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.auth import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter()


# --- Cookie helpers ---

def _is_secure() -> bool:
    return settings.environment != "development"


def _set_auth_cookies(response: Response, access_token: str, refresh_token: str) -> None:
    secure = _is_secure()
    # Access token: httpOnly, not JS-readable
    response.set_cookie(
        key="ts_access_token",
        value=access_token,
        max_age=900,  # 15 min
        httponly=True,
        samesite="lax",
        secure=secure,
        path="/",
    )
    # Refresh token: httpOnly, scoped to auth endpoints
    response.set_cookie(
        key="ts_refresh_token",
        value=refresh_token,
        max_age=604800,  # 7 days
        httponly=True,
        samesite="lax",
        secure=secure,
        path="/api/v1/auth",
    )
    # Non-sensitive indicator cookie for middleware (JS-readable)
    response.set_cookie(
        key="ts_session",
        value="1",
        max_age=604800,
        httponly=False,
        samesite="lax",
        secure=secure,
        path="/",
    )


def _clear_auth_cookies(response: Response) -> None:
    response.delete_cookie(key="ts_access_token", path="/")
    response.delete_cookie(key="ts_refresh_token", path="/api/v1/auth")
    response.delete_cookie(key="ts_session", path="/")


# --- Schemas ---

class RegisterRequest(BaseModel):
    email: str = Field(..., min_length=5, max_length=255)
    password: str = Field(..., min_length=8, max_length=128)
    full_name: str = Field(..., min_length=1, max_length=200)
    org_name: Optional[str] = Field(None, max_length=200)


class LoginRequest(BaseModel):
    email: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    id: int
    email: str
    full_name: str
    role: str
    org_name: Optional[str]
    is_active: bool

    model_config = {"from_attributes": True}


class RefreshRequest(BaseModel):
    refresh_token: str


# --- Endpoints ---

@router.post("/auth/register", response_model=UserResponse, status_code=201)
async def register(payload: RegisterRequest, request: Request, db: AsyncSession = Depends(get_async_db)):
    """Register a new user."""
    result = await db.execute(select(User).filter(User.email == payload.email))
    existing = result.scalars().first()
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    user = User(
        email=payload.email,
        hashed_password=hash_password(payload.password),
        full_name=payload.full_name,
        org_name=payload.org_name,
        role="analyst",
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    logger.info("User registered: %s (org=%s)", user.email, user.org_name)
    return user


@router.post("/auth/login", response_model=TokenResponse)
async def login(request: Request, payload: LoginRequest, db: AsyncSession = Depends(get_async_db)):
    """Authenticate and return JWT tokens in httpOnly cookies."""
    result = await db.execute(select(User).filter(User.email == payload.email))
    user = result.scalars().first()
    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account is deactivated")

    # Create a new refresh token family for this login
    import uuid
    family_id = str(uuid.uuid4())

    access_token = create_access_token({
        "sub": str(user.id),
        "email": user.email,
        "role": user.role,
    }, token_version=user.token_version or 1)
    refresh_token = create_refresh_token({"sub": str(user.id)}, family_id=family_id)

    # Store the refresh token in DB for rotation tracking
    decoded_refresh = decode_token(refresh_token)
    refresh_record = RefreshToken(
        user_id=user.id,
        token_jti=decoded_refresh["jti"],
        family_id=family_id,
        is_rotated=False,
        is_revoked=False,
    )
    db.add(refresh_record)
    await db.commit()

    logger.info("User logged in: %s", user.email)

    response = TokenResponse(access_token=access_token, refresh_token=refresh_token)
    # Set httpOnly cookies on the response
    from starlette.responses import JSONResponse
    resp = JSONResponse(content=response.model_dump())
    _set_auth_cookies(resp, access_token, refresh_token)
    return resp


@router.post("/auth/refresh", response_model=TokenResponse)
async def refresh(request: Request, payload: RefreshRequest, db: AsyncSession = Depends(get_async_db)):
    """Refresh an access token using a refresh token with rotation and reuse detection."""
    # Try to get refresh token from cookie first, then from body
    token = payload.refresh_token if payload.refresh_token else request.cookies.get("ts_refresh_token")
    if not token:
        raise HTTPException(status_code=401, detail="No refresh token provided")

    decoded = decode_token(token)
    if not decoded or decoded.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    user_id = decoded.get("sub")
    token_jti = decoded.get("jti")
    family_id = decoded.get("family")

    if not user_id or not token_jti or not family_id:
        raise HTTPException(status_code=401, detail="Invalid token claims")

    # Look up the presented token in the family
    result = await db.execute(
        select(RefreshToken).filter(RefreshToken.token_jti == token_jti)
    )
    stored_token = result.scalars().first()

    if stored_token:
        # Token found — check if it was already rotated (reuse attack)
        if stored_token.is_rotated:
            # Reuse detected — revoke entire family
            logger.warning(
                "Refresh token reuse detected for user %s, family %s",
                user_id, family_id,
            )
            from sqlalchemy import update
            await db.execute(
                update(RefreshToken)
                .where(RefreshToken.family_id == family_id)
                .values(
                    is_revoked=True,
                    revoked_at=datetime.now(timezone.utc),
                )
            )
            await db.commit()
            raise HTTPException(status_code=401, detail="Refresh token reuse detected — session revoked")

        # Mark old token as rotated
        stored_token.is_rotated = True
        stored_token.rotated_at = datetime.now(timezone.utc)
        # Don't commit yet — we'll store the new token atomically below
    else:
        # Token not found — could be first use after migration, allow it
        # Store it as rotated immediately (it's being consumed now)
        new_record = RefreshToken(
            user_id=int(user_id),
            token_jti=token_jti,
            family_id=family_id,
            is_rotated=True,
            rotated_at=datetime.now(timezone.utc),
        )
        db.add(new_record)
        # We must NOT commit yet — we'll create the new token below,
        # store its record as is_rotated=False, and commit atomically.

    user_result = await db.execute(select(User).filter(User.id == int(user_id)))
    user = user_result.scalars().first()
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found or inactive")

    access_token = create_access_token({
        "sub": str(user.id),
        "email": user.email,
        "role": user.role,
    }, token_version=user.token_version or 1)
    new_refresh = create_refresh_token({"sub": str(user.id)}, family_id=family_id)

    # Store the new refresh token record (is_rotated=False so next refresh works)
    decoded_new = decode_token(new_refresh)
    new_token_record = RefreshToken(
        user_id=int(user_id),
        token_jti=decoded_new["jti"],
        family_id=family_id,
        is_rotated=False,
    )
    db.add(new_token_record)
    await db.commit()

    from starlette.responses import JSONResponse
    resp = JSONResponse(content=TokenResponse(access_token=access_token, refresh_token=new_refresh).model_dump())
    _set_auth_cookies(resp, access_token, new_refresh)
    return resp


@router.post("/auth/logout")
async def logout(request: Request, db: AsyncSession = Depends(get_async_db)):
    """Clear auth cookies and revoke tokens."""
    from starlette.responses import JSONResponse

    # Try to revoke the current access token
    token = request.cookies.get("ts_access_token")
    if token:
        decoded = decode_token(token)
        if decoded and decoded.get("jti") and decoded.get("sub"):
            revoked = RevokedSession(
                user_id=int(decoded["sub"]),
                token_jti=decoded["jti"],
                token_type="access",
            )
            db.add(revoked)

    # Revoke all refresh tokens for this user
    refresh_token = request.cookies.get("ts_refresh_token")
    if refresh_token:
        decoded = decode_token(refresh_token)
        if decoded and decoded.get("sub"):
            user_id = int(decoded["sub"])
            from sqlalchemy import update
            await db.execute(
                update(RefreshToken)
                .where(RefreshToken.user_id == user_id)
                .where(~RefreshToken.is_revoked)
                .values(
                    is_revoked=True,
                    revoked_at=datetime.now(timezone.utc),
                )
            )

    await db.commit()

    resp = JSONResponse(content={"message": "Logged out"})
    _clear_auth_cookies(resp)
    return resp


@router.get("/auth/me", response_model=UserResponse)
async def me(current_user: User = Depends(get_current_user)):
    """Get current authenticated user info."""
    return current_user
