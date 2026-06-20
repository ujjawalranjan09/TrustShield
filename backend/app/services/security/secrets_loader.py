"""AWS Secrets Manager integration for TrustShield.

Hydrates environment variables from Secrets Manager at startup, before
the Settings singleton is instantiated.  This avoids the bootstrap
paradox (Settings reads env vars, but env vars come from Secrets Manager).

Usage:
    Set ``SECRETS_MANAGER_PREFIX`` env var to enable.  The loader fetches
    secrets under that prefix and injects them into ``os.environ``.
"""

from __future__ import annotations

import json
import logging
import os

logger = logging.getLogger(__name__)


class SecretsLoader:
    """Fetch key/value pairs from AWS Secrets Manager."""

    def __init__(self, prefix: str, region: str = "ap-south-1", client=None):
        self._prefix = prefix
        self._region = region
        self._client = client

    def _get_client(self):
        if self._client is not None:
            return self._client
        try:
            import boto3
            self._client = boto3.client("secretsmanager", region_name=self._region)
        except ImportError:
            raise RuntimeError("boto3 is required for SecretsLoader")
        return self._client

    def load(self) -> dict[str, str]:
        """Fetch secrets under the prefix and return a flat dict.

        Supports:
        - Single secret: ``{prefix}`` → parse as JSON key/values
        - Multiple secrets: ``{prefix}/db``, ``{prefix}/redis``, ``{prefix}/app``
        """
        client = self._get_client()
        result: dict[str, str] = {}

        # Try the prefix as a single secret first
        try:
            response = client.get_secret_value(SecretId=self._prefix)
            data = json.loads(response["SecretString"])
            if isinstance(data, dict):
                result.update({k: str(v) for k, v in data.items()})
            return result
        except client.exceptions.ResourceNotFoundException:
            pass
        except Exception as exc:
            logger.debug("Secret %s not found as single secret: %s", self._prefix, exc)

        # Try common sub-keys
        for suffix in ("db", "redis", "app"):
            secret_id = f"{self._prefix}/{suffix}"
            try:
                response = client.get_secret_value(SecretId=secret_id)
                data = json.loads(response["SecretString"])
                if isinstance(data, dict):
                    result.update({k: str(v) for k, v in data.items()})
            except Exception as exc:
                logger.debug("Secret %s not found: %s", secret_id, exc)

        return result

    @staticmethod
    def apply_to_environ(secrets: dict[str, str], overwrite: bool = False) -> None:
        """Inject secrets into ``os.environ``.

        If ``overwrite=False`` (default), existing env vars are preserved
        (environment wins over Secrets Manager).
        """
        for key, value in secrets.items():
            if overwrite or key not in os.environ:
                os.environ[key] = value


_loaded = False


def _maybe_hydrate_secrets() -> None:
    """Hydrate secrets from AWS Secrets Manager if configured.

    Called at module import time, before Settings() is instantiated.
    Reads ``SECRETS_MANAGER_PREFIX`` directly from ``os.environ`` to
    avoid the bootstrap paradox.
    """
    global _loaded
    if _loaded:
        return

    prefix = os.environ.get("SECRETS_MANAGER_PREFIX", "")
    if not prefix:
        return

    region = os.environ.get("SECRETS_MANAGER_REGION", "ap-south-1")

    logger.info("Loading secrets from AWS Secrets Manager (prefix=%s)", prefix)
    try:
        loader = SecretsLoader(prefix=prefix, region=region)
        secrets = loader.load()
        loader.apply_to_environ(secrets, overwrite=False)
        logger.info("Loaded %d secret keys from Secrets Manager", len(secrets))
    except Exception as exc:
        logger.error("Failed to load secrets from Secrets Manager: %s", exc)

    _loaded = True


# Hydrate on import — runs once when the module is first loaded
_maybe_hydrate_secrets()
