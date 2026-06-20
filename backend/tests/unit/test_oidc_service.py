"""Unit tests for OIDC service flows."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
from base64 import urlsafe_b64encode

from app.services.auth.sso_router import (
    _validate_id_token,
    _oidc_discover,
    _oidc_exchange_code,
)


def _b64url(n):
    return urlsafe_b64encode(n.to_bytes((n.bit_length() + 7) // 8, "big")).rstrip(b"=").decode()


def _make_jwks():
    """Create a minimal JWKS-like dict for testing."""
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_key = private_key.public_key()
    nums = public_key.public_numbers()

    private_pem = private_key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )

    jwk_dict = {
        "kty": "RSA",
        "kid": "test-key-1",
        "use": "sig",
        "n": _b64url(nums.n),
        "e": _b64url(nums.e),
    }
    return jwk_dict, private_pem


def _sign_token(claims: dict, private_pem: bytes, kid: str = "test-key-1") -> str:
    """Sign a token using PEM private key bytes."""
    from jose import jwt as jose_jwt
    return jose_jwt.encode(claims, private_pem, algorithm="RS256", headers={"kid": kid})


@pytest.mark.asyncio
async def test_code_exchange_returns_tokens():
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "access_token": "mock-access",
        "id_token": "mock-id-token",
        "token_type": "bearer",
    }
    mock_response.raise_for_status = MagicMock()

    with patch("app.services.auth.sso_router.httpx.AsyncClient") as mock_client_cls:
        instance = AsyncMock()
        instance.post = AsyncMock(return_value=mock_response)
        instance.get = AsyncMock(return_value=mock_response)
        instance.__aenter__ = AsyncMock(return_value=instance)
        instance.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = instance

        result = await _oidc_exchange_code(
            code="test-code",
            config={"token_endpoint": "https://idp.example.com/token"},
            redirect_uri="https://app.example.com/callback",
            client_id="my-client",
            client_secret="my-secret",
        )

    assert result["access_token"] == "mock-access"
    assert result["id_token"] == "mock-id-token"


def test_invalid_aud_rejected():
    jwk_dict, private_pem = _make_jwks()
    jwks = {"keys": [jwk_dict]}

    token = _sign_token(
        {
            "sub": "user-123",
            "email": "user@test.com",
            "iss": "https://idp.example.com",
            "aud": "wrong-client",
            "exp": 9999999999,
        },
        private_pem,
    )

    with pytest.raises(Exception):
        _validate_id_token(
            token,
            jwks,
            expected_iss="https://idp.example.com",
            expected_aud="correct-client",
        )


def test_valid_id_token_accepted():
    jwk_dict, private_pem = _make_jwks()
    jwks = {"keys": [jwk_dict]}

    token = _sign_token(
        {
            "sub": "user-123",
            "email": "user@test.com",
            "iss": "https://idp.example.com",
            "aud": "my-client",
            "exp": 9999999999,
        },
        private_pem,
    )

    result = _validate_id_token(
        token, jwks,
        expected_iss="https://idp.example.com",
        expected_aud="my-client",
    )
    assert result["sub"] == "user-123"
    assert result["email"] == "user@test.com"


@pytest.mark.asyncio
async def test_oidc_discover_fetches_well_known():
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "issuer": "https://idp.example.com",
        "authorization_endpoint": "https://idp.example.com/authorize",
        "token_endpoint": "https://idp.example.com/token",
        "jwks_uri": "https://idp.example.com/.well-known/jwks.json",
    }
    mock_resp.raise_for_status = MagicMock()

    with patch("app.services.auth.sso_router.httpx.AsyncClient") as mock_client_cls:
        instance = AsyncMock()
        instance.get = AsyncMock(return_value=mock_resp)
        instance.__aenter__ = AsyncMock(return_value=instance)
        instance.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = instance

        result = await _oidc_discover("https://idp.example.com")

    assert result["issuer"] == "https://idp.example.com"
    assert "authorization_endpoint" in result
