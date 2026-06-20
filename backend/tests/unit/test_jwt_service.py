"""Unit tests for JWT service."""

from app.services.auth.jwt_service import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)


def test_password_hash():
    hashed = hash_password("testpassword123")
    assert hashed != "testpassword123"
    assert verify_password("testpassword123", hashed) is True
    assert verify_password("wrongpassword", hashed) is False


def test_access_token():
    token = create_access_token({"sub": "1", "email": "test@test.com", "role": "analyst"})
    payload = decode_token(token)
    assert payload is not None
    assert payload["sub"] == "1"
    assert payload["type"] == "access"


def test_refresh_token():
    token = create_refresh_token({"sub": "1"})
    payload = decode_token(token)
    assert payload is not None
    assert payload["type"] == "refresh"


def test_invalid_token():
    payload = decode_token("invalid.token.here")
    assert payload is None
