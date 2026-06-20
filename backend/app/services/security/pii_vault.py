"""PII tokenization and encryption service.

Implements envelope encryption with AES-256-GCM for field-level encryption
and HMAC-SHA256 for deterministic tokenization.

Architecture:
  - Tokenization: HMAC-SHA256 (deterministic) for lookup-able tokens (e.g., phone)
  - Encryption: AES-256-GCM (non-deterministic) for field-level encryption
  - KMS-backed envelope encryption via KeyProvider (Phase C)

Versioned ciphertext format (Phase C):
  byte 0       = 1 (version marker)
  byte 1       = len(wrapped_dek) as uint8
  bytes 2..N   = wrapped_dek
  bytes N+1..  = nonce + aesgcm_ciphertext + tag

Legacy Phase B format (detected automatically):
  ENC: prefix followed by base64(nonce || ciphertext || tag)
"""

import base64
import hashlib
import hmac
import logging
import os
from typing import Optional, Tuple

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.config import settings

logger = logging.getLogger(__name__)

# Nonce length for AES-GCM
_NONCE_LENGTH = 12
_TAG_LENGTH = 16  # GCM auth tag length
# Prefix marker for legacy envelope-encrypted values
_ENC_PREFIX = "ENC:"
# Versioned envelope marker
_VERSION = 1
_MAX_WRAPPED_DEK_LEN = 255  # uint8 max


def _get_encryption_key() -> Optional[bytes]:
    """Get the PII encryption key as 32 bytes.

    Returns None if not configured or invalid.
    """
    key_b64 = settings.pii_encryption_key
    if not key_b64:
        return None
    try:
        key = base64.b64decode(key_b64)
    except Exception:
        logger.error("PII_ENCRYPTION_KEY is not valid base64")
        return None
    if len(key) != 32:
        logger.error(
            "PII_ENCRYPTION_KEY must decode to exactly 32 bytes (got %d). "
            "Generate with: python -c \"import os,base64; print(base64.b64encode(os.urandom(32)).decode())\"",
            len(key),
        )
        return None
    return key


def _get_pepper() -> bytes:
    """Get a pepper for HMAC tokenization.

    Derives from the encryption key, or uses a SHA-256 of the string
    'trustshield-pii-pepper' if no key is configured (dev fallback).
    """
    key = _get_encryption_key()
    if key:
        return hashlib.sha256(b"pii-tokens:" + key).digest()[:32]
    return hashlib.sha256(b"trustshield-pii-pepper-dev").digest()


def tokenize(value: str, value_type: str = "generic") -> str:
    """Deterministic tokenization via HMAC-SHA256.

    Args:
        value: The plaintext value to tokenize.
        value_type: Context string for domain separation ("phone", "email",
                    "upi", "generic").

    Returns:
        Hex-encoded HMAC token, prefixed with ``tkn_{value_type}_``.
    """
    pepper = _get_pepper()
    msg = f"{value_type}:{value}".encode("utf-8")
    token = hmac.new(pepper, msg, hashlib.sha256).hexdigest()[:32]
    return f"tkn_{value_type}_{token}"


# ---------------------------------------------------------------------------
# Versioned envelope helpers
# ---------------------------------------------------------------------------


def _is_versioned(blob: bytes) -> bool:
    """Check if a raw ciphertext blob uses the Phase C versioned format."""
    return len(blob) >= 2 and blob[0] == _VERSION


def _is_legacy(value: str) -> bool:
    """Check if a string is a Phase B legacy ciphertext (ENC: prefix)."""
    if not isinstance(value, str):
        return False
    if value.startswith(_ENC_PREFIX):
        return True
    try:
        data = base64.b64decode(value, validate=True)
        return not _is_versioned(data)
    except Exception:
        return False


def _build_versioned_envelope(dek: bytes, wrapped_dek: bytes, plaintext: bytes) -> bytes:
    """Build a versioned ciphertext envelope.

    Format: version(1) + len(wrapped_dek)(1) + wrapped_dek + nonce + aesgcm(tag)
    """
    if len(wrapped_dek) > _MAX_WRAPPED_DEK_LEN:
        raise ValueError(f"wrapped_dek too large: {len(wrapped_dek)} bytes")
    aesgcm = AESGCM(dek)
    nonce = os.urandom(_NONCE_LENGTH)
    ciphertext = aesgcm.encrypt(nonce, plaintext, None)
    return bytes([_VERSION, len(wrapped_dek)]) + wrapped_dek + nonce + ciphertext


def _parse_versioned_envelope(blob: bytes) -> Tuple[bytes, bytes, bytes]:
    """Parse a versioned ciphertext envelope.

    Returns: (wrapped_dek, nonce, ciphertext_with_tag)
    """
    version = blob[0]
    if version != _VERSION:
        raise ValueError(f"Unknown ciphertext version: {version}")
    wrapped_dek_len = blob[1]
    wrapped_dek = blob[2:2 + wrapped_dek_len]
    rest = blob[2 + wrapped_dek_len:]
    if len(rest) < _NONCE_LENGTH + _TAG_LENGTH:
        raise ValueError("Ciphertext too short")
    nonce = rest[:_NONCE_LENGTH]
    ct_with_tag = rest[_NONCE_LENGTH:]
    return wrapped_dek, nonce, ct_with_tag


def _decrypt_versioned(blob: bytes) -> bytes:
    """Decrypt a versioned ciphertext blob. Returns plaintext bytes."""
    from app.services.security.kms_provider import get_provider
    provider = get_provider()
    wrapped_dek, nonce, ct_with_tag = _parse_versioned_envelope(blob)
    dek = provider.unwrap_dek(wrapped_dek)
    aesgcm = AESGCM(dek)
    return aesgcm.decrypt(nonce, ct_with_tag, None)


def _decrypt_legacy(raw: bytes) -> bytes:
    """Decrypt a Phase B legacy ciphertext. Returns plaintext bytes."""
    key = _get_encryption_key()
    if key is None:
        raise RuntimeError("No encryption key configured for legacy decryption")
    if len(raw) < _NONCE_LENGTH + _TAG_LENGTH:
        raise ValueError("Legacy ciphertext too short")
    nonce = raw[:_NONCE_LENGTH]
    ct = raw[_NONCE_LENGTH:]
    aesgcm = AESGCM(key)
    return aesgcm.decrypt(nonce, ct, None)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def encrypt_field(value: str) -> Optional[str]:
    """Encrypt a value using AES-256-GCM with KMS-backed envelope encryption.

    Returns a base64-encoded versioned ciphertext, or None if encryption is
    not configured.

    Format: base64(version + len(wrapped_dek) + wrapped_dek + nonce + ciphertext + tag)
    """
    try:
        from app.services.security.kms_provider import get_provider
        provider = get_provider()
        dek, wrapped_dek = provider.generate_dek()
        blob = _build_versioned_envelope(dek, wrapped_dek, value.encode("utf-8"))
        return base64.b64encode(blob).decode("utf-8")
    except Exception as exc:
        logger.error("Encryption failed: %s", exc)
        return None


def decrypt_field(ciphertext_b64: str) -> Optional[str]:
    """Decrypt a value encrypted with ``encrypt_field``.

    Supports both Phase C versioned envelopes and Phase B legacy format.
    Returns the original plaintext, or None if decryption fails.
    """
    raw_b64 = ciphertext_b64
    if raw_b64.startswith(_ENC_PREFIX):
        raw_b64 = raw_b64[len(_ENC_PREFIX):]

    try:
        blob = base64.b64decode(raw_b64)
    except Exception:
        return None

    try:
        if _is_versioned(blob):
            plaintext = _decrypt_versioned(blob)
        else:
            plaintext = _decrypt_legacy(blob)
        return plaintext.decode("utf-8")
    except Exception as exc:
        logger.error("Decryption failed: %s", exc)
        return None


def decrypt_field_with_reencrypt(ciphertext_b64: str) -> Tuple[Optional[str], Optional[str]]:
    """Decrypt and lazily re-encrypt legacy ciphertext to the new envelope format.

    Returns:
        ``(plaintext, new_ciphertext_b64)`` — the new ciphertext is non-None
        only when the input was legacy format and re-encryption succeeded.
        Callers should persist the new ciphertext on next DB flush.
    """
    raw_b64 = ciphertext_b64
    if raw_b64.startswith(_ENC_PREFIX):
        raw_b64 = raw_b64[len(_ENC_PREFIX):]

    try:
        blob = base64.b64decode(raw_b64)
    except Exception:
        return None, None

    try:
        if _is_versioned(blob):
            plaintext = _decrypt_versioned(blob)
            return plaintext.decode("utf-8"), None
        else:
            plaintext = _decrypt_legacy(blob)
            # Re-encrypt with new envelope
            new_ct = encrypt_field(plaintext.decode("utf-8"))
            return plaintext.decode("utf-8"), new_ct
    except Exception as exc:
        logger.error("Decryption failed: %s", exc)
        return None, None


def is_encrypted(value: str) -> bool:
    """Check if a string is an envelope-encrypted value (legacy or versioned)."""
    if not isinstance(value, str):
        return False
    # Check legacy ENC: prefix
    if value.startswith(_ENC_PREFIX):
        raw = value[len(_ENC_PREFIX):]
        try:
            data = base64.b64decode(raw, validate=True)
        except Exception:
            return False
        return len(data) >= _NONCE_LENGTH + _TAG_LENGTH
    # Check versioned base64 blob
    try:
        data = base64.b64decode(value, validate=True)
    except Exception:
        return False
    return _is_versioned(data)


def is_token(value: str) -> bool:
    """Check if a string is a tokenized value."""
    return value.startswith("tkn_")


def encrypt_dict(data: dict, fields: list) -> dict:
    """Encrypt specified fields in a dict in-place.

    Returns the modified dict (same reference).
    """
    for field in fields:
        if field in data and data[field]:
            encrypted = encrypt_field(str(data[field]))
            if encrypted:
                data[field] = encrypted
    return data


def decrypt_dict(data: dict, fields: list) -> dict:
    """Decrypt specified fields in a dict in-place.

    Returns the modified dict (same reference).
    """
    for field in fields:
        if field in data and data[field] and is_encrypted(str(data[field])):
            decrypted = decrypt_field(str(data[field]))
            if decrypted:
                data[field] = decrypted
    return data
