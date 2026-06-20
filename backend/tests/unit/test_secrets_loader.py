"""Unit tests for the Secrets Manager loader."""

import json
import os
from unittest.mock import MagicMock

import pytest


class TestSecretsLoader:
    def test_load_populates_environ(self, monkeypatch):
        from app.services.security.secrets_loader import SecretsLoader

        secret_data = {"JWT_SECRET": "test-secret-123", "DATABASE_URL": "postgresql://test"}
        mock_client = MagicMock()
        mock_client.get_secret_value.return_value = {
            "SecretString": json.dumps(secret_data)
        }

        loader = SecretsLoader(prefix="trustshield/test/app", client=mock_client)
        secrets = loader.load()
        assert secrets["JWT_SECRET"] == "test-secret-123"
        assert secrets["DATABASE_URL"] == "postgresql://test"

    def test_env_overrides_win(self, monkeypatch):
        from app.services.security.secrets_loader import SecretsLoader

        monkeypatch.setenv("JWT_SECRET", "original-value")
        secret_data = {"JWT_SECRET": "from-secrets-manager", "OTHER_KEY": "new"}
        mock_client = MagicMock()
        mock_client.get_secret_value.return_value = {
            "SecretString": json.dumps(secret_data)
        }

        loader = SecretsLoader(prefix="trustshield/test/app", client=mock_client)
        secrets = loader.load()
        loader.apply_to_environ(secrets, overwrite=False)

        # Original value preserved
        assert os.environ["JWT_SECRET"] == "original-value"
        # New key added
        assert os.environ["OTHER_KEY"] == "new"

    def test_overwrite_mode_replaces_values(self, monkeypatch):
        from app.services.security.secrets_loader import SecretsLoader

        monkeypatch.setenv("JWT_SECRET", "original-value")
        secret_data = {"JWT_SECRET": "from-secrets-manager"}
        mock_client = MagicMock()
        mock_client.get_secret_value.return_value = {
            "SecretString": json.dumps(secret_data)
        }

        loader = SecretsLoader(prefix="trustshield/test/app", client=mock_client)
        secrets = loader.load()
        loader.apply_to_environ(secrets, overwrite=True)

        assert os.environ["JWT_SECRET"] == "from-secrets-manager"

    def test_dev_no_prefix_skips(self, monkeypatch):
        import app.services.security.secrets_loader as mod

        monkeypatch.delenv("SECRETS_MANAGER_PREFIX", raising=False)
        mod._loaded = False

        mock_loader_cls = MagicMock()
        mock_loader_cls.return_value.load.return_value = {}
        monkeypatch.setattr("app.services.security.secrets_loader.SecretsLoader", mock_loader_cls)

        mod._maybe_hydrate_secrets()
        mock_loader_cls.assert_not_called()

    def test_tolerates_missing_secret(self):
        from app.services.security.secrets_loader import SecretsLoader

        from botocore.exceptions import ClientError
        mock_client = MagicMock()
        mock_client.exceptions.ResourceNotFoundException = type("ResourceNotFoundException", (Exception,), {})
        mock_client.get_secret_value.side_effect = mock_client.exceptions.ResourceNotFoundException(
            {"Error": {"Code": "ResourceNotFoundException"}}, "GetSecretValue"
        )

        loader = SecretsLoader(prefix="trustshield/test/nonexistent", client=mock_client)
        secrets = loader.load()
        assert secrets == {}
