"""Tests for PII vault — tokenization, encryption, and redaction."""

import base64
import os

import pytest

from app.services.security.pii_vault import (
    decrypt_field,
    encrypt_field,
    is_encrypted,
    is_token,
    tokenize,
)
from app.utils.pii import contains_pii, redact


class TestPIIVault:
    def test_tokenize_deterministic(self):
        """Tokenization should be deterministic for same input."""
        token1 = tokenize("9876543210", "phone")
        token2 = tokenize("9876543210", "phone")
        assert token1 == token2
        assert token1.startswith("tkn_phone_")

    def test_tokenize_different_types(self):
        """Different value_types should produce different tokens for same value."""
        t1 = tokenize("test@example.com", "email")
        t2 = tokenize("test@example.com", "generic")
        assert t1 != t2

    def test_encrypt_decrypt_roundtrip(self, monkeypatch):
        """Encrypt then decrypt should return original value."""
        # Set a test encryption key
        test_key = base64.b64encode(b"x" * 32).decode()
        monkeypatch.setattr(
            "app.services.security.pii_vault.settings.pii_encryption_key", test_key
        )

        original = "victim-phone-9876543210"
        encrypted = encrypt_field(original)
        assert encrypted is not None
        assert encrypted != original
        assert is_encrypted(encrypted)

        decrypted = decrypt_field(encrypted)
        assert decrypted == original

    def test_encrypt_decrypt_not_configured(self):
        """Encrypt should return None when no key is configured."""
        result = encrypt_field("test")
        assert result is None

    def test_is_token_true(self):
        """is_token should return True for tokenized values."""
        assert is_token("tkn_phone_abc123def456") is True

    def test_is_token_false(self):
        """is_token should return False for plain values."""
        assert is_token("9876543210") is False


class TestPIIRedaction:
    def test_redact_phone(self):
        """Phone numbers should be redacted."""
        result = redact("Call me at 9876543210")
        assert "9876543210" not in result
        assert "[REDACTED]" in result

    def test_redact_vpa(self):
        """UPI VPAs should be redacted."""
        result = redact("Send money to user@ybl")
        assert "user@ybl" not in result
        assert "[REDACTED]" in result

    def test_redact_email(self):
        """Emails should be redacted."""
        result = redact("Email me at test@example.com")
        assert "test@example.com" not in result
        assert "[REDACTED]" in result

    def test_redact_ifsc(self):
        """IFSC codes should be redacted."""
        result = redact("IFSC: SBIN0001234")
        assert "SBIN0001234" not in result

    def test_redact_multiple(self):
        """Multiple PII instances should all be redacted."""
        text = "Phone: 9876543210, UPI: user@paytm, Email: a@b.com"
        result = redact(text)
        # Should have exactly 3 [REDACTED] markers
        assert result.count("[REDACTED]") == 3

    def test_contains_pii_true(self):
        """contains_pii should detect PII."""
        assert contains_pii("Call 9876543210") is True

    def test_contains_pii_false(self):
        """contains_pii should return False for clean text."""
        assert contains_pii("Hello, how are you?") is False