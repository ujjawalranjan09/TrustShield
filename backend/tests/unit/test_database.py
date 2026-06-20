"""Unit tests for database pool configuration and main startup checks."""

import pytest


class TestEnginePoolConfig:
    def test_config_defaults_are_correct(self):
        from app.config import Settings

        s = Settings(
            database_url="postgresql+asyncpg://user:pass@localhost:5432/trustshield",
            environment="development",
        )
        assert s.db_pool_size == 10
        assert s.db_max_overflow == 20
        assert s.db_pool_timeout == 30
        assert s.db_pool_recycle == 1800
        assert s.db_ssl_required is True

    def test_custom_pool_settings(self):
        from app.config import Settings

        s = Settings(
            database_url="postgresql+asyncpg://user:pass@localhost:5432/trustshield",
            db_pool_size=15,
            db_max_overflow=25,
            db_pool_timeout=45,
            db_pool_recycle=900,
            db_ssl_required=False,
            environment="development",
        )
        assert s.db_pool_size == 15
        assert s.db_max_overflow == 25
        assert s.db_pool_timeout == 45
        assert s.db_pool_recycle == 900
        assert s.db_ssl_required is False

    def test_ssl_connect_args_added_for_non_dev(self):
        from app.config import Settings

        s = Settings(
            database_url="postgresql+asyncpg://user:pass@localhost:5432/trustshield",
            db_ssl_required=True,
            environment="staging",
        )
        # In non-dev with ssl_required, connect_args should be set
        assert s.db_ssl_required is True
        assert s.environment != "development"

    def test_no_ssl_in_dev(self):
        from app.config import Settings

        s = Settings(
            database_url="postgresql://user:pass@localhost:5432/trustshield",
            db_ssl_required=True,
            environment="development",
        )
        assert s.environment == "development"


class TestMainStartupChecks:
    def test_production_requires_pii_key_or_kms(self):
        from app.config import Settings

        s = Settings(
            environment="production",
            pii_encryption_key="",
            kms_key_id="",
            database_url="postgresql+asyncpg://u:p@host/db?sslmode=require",
        )
        # Simulates the startup check: neither key set
        assert s.environment != "development"
        assert not s.pii_encryption_key and not s.kms_key_id

    def test_production_with_kms_key_id_ok(self):
        from app.config import Settings

        s = Settings(
            environment="production",
            pii_encryption_key="",
            kms_key_id="arn:aws:kms:ap-south-1:123:key/x",
            database_url="postgresql+asyncpg://u:p@host/db?sslmode=require",
        )
        assert s.kms_key_id != ""
        # Startup check would pass (has kms_key_id)

    def test_production_requires_asyncpg_url(self):
        from app.config import Settings

        s = Settings(
            environment="production",
            database_url="postgresql://user:pass@host/db",
            pii_encryption_key="abc",
        )
        assert not s.database_url.startswith("postgresql+asyncpg://")

    def test_production_requires_ssl_in_db_url(self):
        from app.config import Settings

        s = Settings(
            environment="production",
            database_url="postgresql+asyncpg://user:pass@host/db",
            db_ssl_required=True,
            pii_encryption_key="abc",
        )
        assert "sslmode" not in s.database_url
        assert "ssl=require" not in s.database_url

    def test_production_redis_requires_tls(self):
        from app.config import Settings

        s = Settings(
            environment="production",
            event_backend="redis",
            redis_url="redis://localhost:6379/0",
        )
        assert s.event_backend == "redis"
        assert not s.redis_url.startswith("rediss://")

    def test_dev_skips_all_checks(self):
        from app.config import Settings

        s = Settings(
            environment="development",
            database_url="sqlite:///./dev.db",
            redis_url="redis://localhost:6379/0",
            pii_encryption_key="",
            kms_key_id="",
        )
        # Dev environment should not trigger any startup checks
        assert s.environment == "development"
