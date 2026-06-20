"""Unit tests for the KMS-backed key provider."""

import base64
import os

import pytest


@pytest.fixture(autouse=True)
def _reset_provider():
    """Reset the provider singleton between tests."""
    import app.services.security.kms_provider as mod
    mod._provider = None
    yield
    mod._provider = None


def _make_settings(pii_key="", kms_key_id=""):
    return type("S", (), {"pii_encryption_key": pii_key, "kms_key_id": kms_key_id, "kms_region": "ap-south-1", "aws_access_key_id": "", "aws_secret_access_key": ""})()


class TestLocalProviderRoundtrip:
    def test_generate_and_unwrap_returns_same_dek(self, monkeypatch):
        from app.services.security.kms_provider import LocalKeyProvider

        key_b64 = base64.b64encode(os.urandom(32)).decode()
        monkeypatch.setattr("app.services.security.kms_provider.settings", _make_settings(pii_key=key_b64))

        provider = LocalKeyProvider()
        dek, wrapped = provider.generate_dek()
        unwrapped = provider.unwrap_dek(wrapped)
        assert dek == unwrapped
        assert len(dek) == 32

    def test_different_calls_produce_different_keys(self, monkeypatch):
        from app.services.security.kms_provider import LocalKeyProvider

        key_b64 = base64.b64encode(os.urandom(32)).decode()
        monkeypatch.setattr("app.services.security.kms_provider.settings", _make_settings(pii_key=key_b64))

        provider = LocalKeyProvider()
        _, wrapped1 = provider.generate_dek()
        _, wrapped2 = provider.generate_dek()
        assert wrapped1 != wrapped2


class TestProviderResolver:
    def test_uses_local_when_no_kms_key(self, monkeypatch):
        from app.services.security.kms_provider import get_provider, LocalKeyProvider

        key_b64 = base64.b64encode(os.urandom(32)).decode()
        monkeypatch.setattr("app.services.security.kms_provider.settings", _make_settings(pii_key=key_b64))

        provider = get_provider()
        assert isinstance(provider, LocalKeyProvider)

    def test_uses_kms_when_key_id_set(self, monkeypatch):
        from app.services.security.kms_provider import get_provider, KMSKeyProvider

        monkeypatch.setattr("app.services.security.kms_provider.settings", _make_settings(kms_key_id="arn:aws:kms:ap-south-1:123456:key/test"))

        provider = get_provider()
        assert isinstance(provider, KMSKeyProvider)


class TestLegacyLazyReencrypt:
    def test_legacy_decrypt_and_reencrypt(self, monkeypatch):
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM

        key = os.urandom(32)
        key_b64 = base64.b64encode(key).decode()

        # Create a Phase B legacy ciphertext
        aesgcm = AESGCM(key)
        nonce = os.urandom(12)
        plaintext = "9876543210"
        ct = aesgcm.encrypt(nonce, plaintext.encode(), None)
        legacy_b64 = base64.b64encode(nonce + ct).decode()
        legacy_value = "ENC:" + legacy_b64

        mock_settings = _make_settings(pii_key=key_b64)

        # Reload modules, then patch the freshly-imported settings
        import importlib
        import app.services.security.kms_provider as kms_mod
        import app.services.security.pii_vault as vault_mod
        importlib.reload(kms_mod)
        importlib.reload(vault_mod)
        monkeypatch.setattr(kms_mod, "settings", mock_settings)
        monkeypatch.setattr(vault_mod, "settings", mock_settings)
        kms_mod._provider = None

        decrypted, new_ct = vault_mod.decrypt_field_with_reencrypt(legacy_value)
        assert decrypted == plaintext
        assert new_ct is not None
        assert new_ct != legacy_value

        # Re-decrypt the new ciphertext — should work without legacy path
        decrypted2 = vault_mod.decrypt_field(new_ct)
        assert decrypted2 == plaintext

    def test_versioned_ciphertext_no_reencrypt(self, monkeypatch):
        key = os.urandom(32)
        key_b64 = base64.b64encode(key).decode()

        mock_settings = _make_settings(pii_key=key_b64)

        import importlib
        import app.services.security.kms_provider as kms_mod
        import app.services.security.pii_vault as vault_mod
        importlib.reload(kms_mod)
        importlib.reload(vault_mod)
        monkeypatch.setattr(kms_mod, "settings", mock_settings)
        monkeypatch.setattr(vault_mod, "settings", mock_settings)
        kms_mod._provider = None

        # Encrypt with the new provider
        encrypted = vault_mod.encrypt_field("test-value")
        assert encrypted is not None

        decrypted, new_ct = vault_mod.decrypt_field_with_reencrypt(encrypted)
        assert decrypted == "test-value"
        assert new_ct is None  # Already versioned, no re-encryption needed
