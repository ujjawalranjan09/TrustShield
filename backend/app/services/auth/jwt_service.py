"""JWT authentication service."""

import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
from jose import ExpiredSignatureError, JWTError, jwt
from jose.exceptions import JWTClaimsError

SECRET_KEY=os.getenv("JWT_SECRET", "dev-secret-change-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES=30
REFRESH_TOKEN_EXPIRE_DAYS = 7


class TokenError(Exception):
    """Base token error."""
    pass


class TokenExpiredError(TokenError):
    """Token has expired."""
    pass


class TokenMalformedError(TokenError):
    """Token is malformed or invalid."""
    pass


def hash_password(password: str) -> str:
    """Hash a plain-text password."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plain-text password against its hash."""
    return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None, token_version: int = 1) -> str:
    """Create a short-lived access token."""
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode.update({"exp": expire, "type": "access", "ver": token_version})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def create_refresh_token(data: dict, family_id: Optional[str] = None) -> str:
    """Create a long-lived refresh token."""
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    jti = str(uuid.uuid4())
    to_encode.update({
        "exp": expire,
        "type": "refresh",
        "jti": jti,
        "family_id": family_id or str(uuid.uuid4()),
    })
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> Optional[dict]:
    """Decode and validate a JWT token. Returns payload or None.

    Raises:
        TokenExpiredError: if the token has expired.
        TokenMalformedError: if the token is malformed or has invalid claims.
    """
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except ExpiredSignatureError:
        raise TokenExpiredError("Token has expired")
    except (JWTClaimsError, JWTError):
        raise TokenMalformedError("Token is malformed or invalid")
