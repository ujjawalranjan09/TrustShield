"""KMS-backed key provider abstraction.

Provides a ``KeyProvider`` ABC with two concrete implementations:

- ``LocalKeyProvider`` — HKDF-derived DEKs from the local PII encryption key
  (development / single-node deployments).
- ``KMSKeyProvider`` — AWS KMS ``GenerateDataKey`` / ``Decrypt`` calls
  (production, multi-node).

The provider is selected at startup based on ``settings.kms_key_id``.
"""

from __future__ import annotations

import base64
import hashlib
import logging
import os
from abc import ABC, abstractmethod
from typing import Optional, Tuple

from app.config import settings

logger = logging.getLogger(__name__)


class KeyProvider(ABC):
    """Abstract base class for DEK generation and unwrapping."""

    @abstractmethod
    async def generate_dek(self) -> Tuple[bytes, bytes]:
        """Generate a new data-encryption key.

        Returns:
            ``(plaintext_dek, wrapped_dek)`` — the plaintext DEK (32 bytes
            for AES-256) and the opaque wrapped version that gets stored
            alongside the ciphertext.
        """

    @abstractmethod
    async def unwrap_dek(self, wrapped_dek: bytes) -> bytes:
        """Unwrap a previously wrapped DEK to its plaintext form."""

    @abstractmethod
    def master_key_id(self) -> str:
        """Identifier of the backing master key (for audit logging)."""


# ---------------------------------------------------------------------------
# Local (HKDF) implementation — development / single-node
# ---------------------------------------------------------------------------


def _local_master_key() -> Optional[bytes]:
    """Decode the base64 PII encryption key."""
    key_b64 = settings.pii_encryption_key
    if not key_b64:
        return None
    try:
        key = base64.b64decode(key_b64)
    except Exception:
        return None
    if len(key) != 32:
        return None
    return key


class LocalKeyProvider(KeyProvider):
    """HKDF-based provider for development environments.

    DEKs are derived from the local PII encryption key + a random salt.
    No network calls; suitable for single-node / dev deployments.
    """

    _SALT_PREFIX = b"local:"

    def generate_dek(self) -> Tuple[bytes, bytes]:
        master = _local_master_key()
        if master is None:
            raise RuntimeError(
                "PII_ENCRYPTION_KEY must be configured for LocalKeyProvider"
            )
        salt = os.urandom(16)
        dek = self._derive(master, salt)
        wrapped = self._SALT_PREFIX + salt
        return dek, wrapped

    def unwrap_dek(self, wrapped_dek: bytes) -> bytes:
        master = _local_master_key()
        if master is None:
            raise RuntimeError(
                "PII_ENCRYPTION_KEY must be configured for LocalKeyProvider"
            )
        if not wrapped_dek.startswith(self._SALT_PREFIX):
            raise ValueError("Invalid wrapped DEK prefix for LocalKeyProvider")
        salt = wrapped_dek[len(self._SALT_PREFIX):]
        return self._derive(master, salt)

    def master_key_id(self) -> str:
        return "local"

    @staticmethod
    def _derive(master: bytes, salt: bytes) -> bytes:
        """HKDF-SHA256 derive a 32-byte DEK."""
        return hashlib.pbkdf2_hmac("sha256", master, salt, iterations=100_000, dklen=32)


# ---------------------------------------------------------------------------
# AWS KMS implementation — production
# ---------------------------------------------------------------------------


class KMSKeyProvider(KeyProvider):
    """AWS KMS-backed provider for production environments.

    Uses ``GenerateDataKey`` to produce a plaintext DEK and a
    KMS-encrypted wrapped DEK.  The wrapped DEK is stored alongside the
    ciphertext and later ``Decrypt``ed to recover the plaintext DEK.
    """

    def __init__(self, boto3_client=None) -> None:
        self._client = boto3_client
        self._key_id = settings.kms_key_id

    def _get_client(self):
        if self._client is not None:
            return self._client
        try:
            import boto3
            kwargs = {}
            if settings.aws_access_key_id:
                kwargs["aws_access_key_id"] = settings.aws_access_key_id
            if settings.aws_secret_access_key:
                kwargs["aws_secret_access_key"] = settings.aws_secret_access_key
            if settings.kms_region:
                kwargs["region_name"] = settings.kms_region
            self._client = boto3.client("kms", **kwargs)
        except ImportError:
            raise RuntimeError(
                "boto3 is required for KMSKeyProvider. Install with: pip install boto3"
            )
        return self._client

    async def generate_dek(self) -> Tuple[bytes, bytes]:
        client = self._get_client()
        response = client.generate_data_key(
            KeyId=self._key_id,
            KeySpec="AES_256",
        )
        return response["Plaintext"], response["CiphertextBlob"]

    async def unwrap_dek(self, wrapped_dek: bytes) -> bytes:
        client = self._get_client()
        response = client.decrypt(CiphertextBlob=wrapped_dek)
        return response["Plaintext"]

    def master_key_id(self) -> str:
        return self._key_id


# ---------------------------------------------------------------------------
# Provider resolver
# ---------------------------------------------------------------------------


_provider: Optional[KeyProvider] = None


def get_provider() -> KeyProvider:
    """Return the active ``KeyProvider`` singleton.

    Uses ``KMSKeyProvider`` when ``settings.kms_key_id`` is set, otherwise
    falls back to ``LocalKeyProvider``.
    """
    global _provider
    if _provider is None:
        if settings.kms_key_id:
            logger.info("Using KMSKeyProvider (key_id=%s)", settings.kms_key_id)
            _provider = KMSKeyProvider()
        else:
            logger.info("Using LocalKeyProvider (no KMS key configured)")
            _provider = LocalKeyProvider()
    return _provider
