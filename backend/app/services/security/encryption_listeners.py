"""SQLAlchemy event listeners for transparent field-level encryption.

Encrypts specified fields on ``before_insert`` / ``before_update`` and
decrypts them on ``after_load``.  When ``pii_encryption_key`` is empty
(dev mode), the listeners are no-ops and store plaintext.
"""

import logging
from typing import Any, Dict, List

from sqlalchemy import event
from sqlalchemy.orm import Mapper

from app.config import settings
from app.services.security.pii_vault import decrypt_field, encrypt_field

logger = logging.getLogger(__name__)

# Registry of (model_class, field_names) tuples to encrypt
_ENCRYPTED_FIELDS: Dict[Any, List[str]] = {}

# Flag to track if listeners are already registered
_listeners_registered = False

# Cache whether PII encryption is enabled
_PII_ENABLED = False


def is_pii_encryption_enabled() -> bool:
    """Check if PII encryption is configured."""
    global _PII_ENABLED
    return _PII_ENABLED


def register_encrypted_fields(model_class: Any, fields: List[str]) -> None:
    """Register a model class and its fields for transparent encryption.

    Must be called before the model is first loaded.
    Usually called at module import time.

    Args:
        model_class: The SQLAlchemy model class (declarative base subclass).
        fields: List of attribute names on the model to encrypt.
    """
    global _listeners_registered
    _ENCRYPTED_FIELDS[model_class] = fields

    if not _listeners_registered:
        _register_event_listeners()
        _listeners_registered = True


def _register_event_listeners() -> None:
    """Register SQLAlchemy event listeners for all encrypted fields."""

    @event.listens_for(Mapper, "before_insert", propagate=True)
    def encrypt_before_insert(mapper, connection, target) -> None:
        """Encrypt fields before inserting."""
        if not _pii_active():
            return
        fields = _ENCRYPTED_FIELDS.get(type(target))
        if not fields:
            return
        for field_name in fields:
            value = getattr(target, field_name, None)
            if value and not _already_encrypted(str(value)):
                encrypted = encrypt_field(str(value))
                if encrypted:
                    setattr(target, field_name, encrypted)
                    logger.debug("Encrypted %s.%s pre-insert", type(target).__name__, field_name)

    @event.listens_for(Mapper, "before_update", propagate=True)
    def encrypt_before_update(mapper, connection, target) -> None:
        """Encrypt fields before updating."""
        if not _pii_active():
            return
        fields = _ENCRYPTED_FIELDS.get(type(target))
        if not fields:
            return
        for field_name in fields:
            value = getattr(target, field_name, None)
            if value and not _already_encrypted(str(value)):
                encrypted = encrypt_field(str(value))
                if encrypted:
                    setattr(target, field_name, encrypted)
                    logger.debug("Encrypted %s.%s pre-update", type(target).__name__, field_name)

    @event.listens_for(Mapper, "after_load", propagate=True)
    def decrypt_after_load(mapper, connection, target) -> None:
        """Decrypt fields after loading from database."""
        if not _pii_active():
            return
        fields = _ENCRYPTED_FIELDS.get(type(target))
        if not fields:
            return
        for field_name in fields:
            value = getattr(target, field_name, None)
            if value and _already_encrypted(str(value)):
                decrypted = decrypt_field(str(value))
                # Only overwrite with plaintext on success; never wipe on
                # failure — leave the encrypted value in place so a key
                # rotation failure does not silently destroy data.
                if decrypted is not None:
                    setattr(target, field_name, decrypted)
                    logger.debug("Decrypted %s.%s post-load", type(target).__name__, field_name)
                else:
                    logger.error(
                        "Failed to decrypt %s.%s — leaving encrypted value in place "
                        "(possible key rotation issue)",
                        type(target).__name__,
                        field_name,
                    )

    logger.info("PII encryption listeners registered for %d model(s)", len(_ENCRYPTED_FIELDS))


def _pii_active() -> bool:
    """Check if PII encryption should be applied."""
    global _PII_ENABLED
    if not _PII_ENABLED and settings.pii_encryption_key:
        _PII_ENABLED = True
    return _PII_ENABLED


def _already_encrypted(value: str) -> bool:
    """Check if a value is already encrypted (base64 of nonce + ciphertext)."""
    from app.services.security.pii_vault import is_encrypted
    return is_encrypted(value)


# ---------------------------------------------------------------------------
# Convenience: register common models
# ---------------------------------------------------------------------------


def register_default_encrypted_fields() -> None:
    """Register encryption for standard PII fields across models.

    Call this during app startup (in lifespan).
    """
    from app.models.recovery import RecoveryCase
    from app.models.feedback import FeedbackLabel

    register_encrypted_fields(RecoveryCase, ["victim_name", "victim_phone", "scammer_info", "upi_id"])
    register_encrypted_fields(FeedbackLabel, ["analyst_email"])

    logger.info("Default PII encrypted fields registered")