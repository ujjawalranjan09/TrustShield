"""Centralised application settings.

All configuration is loaded from environment variables (with ``.env`` file
fallback) via *pydantic-settings*.  A module-level ``settings`` singleton is
exported so consumers can ``from app.config import settings``.
"""

import logging
import warnings

from pydantic_settings import BaseSettings

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    """Application settings loaded from environment variables / .env file."""

    # Application
    app_name: str = "TrustShield"
    app_version: str = "1.0.0"
    environment: str = "development"
    debug: bool = False

    # API
    api_key: str = ""
    allowed_origins: str = "http://localhost:3000"

    # Database
    database_url: str = "postgresql://user:***@localhost:5432/trustshield"
    db_pool_size: int = 10
    db_max_overflow: int = 20
    db_pool_timeout: int = 30
    db_pool_recycle: int = 1800
    db_ssl_required: bool = True

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # Neo4j
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "password"

    # Kafka
    kafka_bootstrap_servers: str = "localhost:9092"

    # ML Model
    muril_model_path: str = "trustshield/backend/ml/artifacts/muril_scam_classifier/model.onnx"

    # Logging
    log_level: str = "INFO"
    log_format: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

    # Observability
    sentry_dsn: str = ""
    otel_endpoint: str = "http://localhost:4318"

    # ML
    ml_artifacts_dir: str = "ml/artifacts"
    model_version: str = ""
    model_service_url: str = ""
    model_service_timeout_ms: int = 100

    # Voice
    voice_provider: str = "mock"  # mock | whisper | deepgram
    deepgram_api_key: str = ""
    whisper_model_size: str = "base"
    voice_sample_rate: int = 16000
    voice_retain_audio: bool = False

    # Image / QR
    image_qr_decode_enabled: bool = True

    # Cybercrime/1930
    cybercrime_api_url: str = "sandbox"
    cybercrime_api_key: str = ""

    # Events
    event_backend: str = "redis"  # redis | kafka

    # Rate limits
    rate_limit_analyze: str = "100/minute"
    rate_limit_webhook: str = "1000/minute"
    rate_limit_scan: str = "60/minute"
    rate_limit_auth: str = "10/minute"

    # JWT
    jwt_secret: str = ""
    jwt_algorithm: str = "HS256"
    jwt_access_expire_minutes: int = 15
    jwt_refresh_expire_days: int = 7

    # Intervention
    proactive_intervention_enabled: bool = False
    intervention_risk_threshold: float = 0.8

    # DPDP / Compliance
    dpdp_enabled: bool = True
    retention_scan_events_days: int = 730
    retention_recovery_years: int = 7

    # WhatsApp
    whatsapp_verify_token: str = ""
    whatsapp_access_token: str = ""
    whatsapp_phone_number_id: str = ""
    whatsapp_outbound_enabled: bool = False

    # LLM
    llm_api_key: str = ""
    llm_provider: str = "openrouter"  # openrouter | local
    llm_model: str = "anthropic/claude-3.5-sonnet"
    llm_base_url: str = ""
    llm_timeout_seconds: int = 10

    # Export
    export_signing_key: str = ""

    # Billing (Stripe)
    billing_enabled: bool = False
    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""
    stripe_price_id_free: str = ""
    stripe_price_id_pro: str = ""
    stripe_price_id_bank: str = ""
    stripe_price_id_enterprise: str = ""

    # PII Encryption
    pii_encryption_key: str = ""

    # AWS KMS
    kms_key_id: str = ""
    kms_region: str = "ap-south-1"
    aws_access_key_id: str = ""
    aws_secret_access_key: str = ""

    # AWS Secrets Manager
    secrets_manager_prefix: str = ""
    secrets_manager_region: str = "ap-south-1"

    # Celery
    celery_task_eager: bool = False
    celery_deadletter_queue: str = "trustshield-deadletter"

    # Reputation
    reputation_decay_days: int = 180

    # Ring detection
    ring_min_entities: int = 5
    ring_min_reports: int = 10
    ring_detect_interval_minutes: int = 15

    # Cell / Regional Data Residency
    cell_region: str = "ap-south-1"
    cell_routing_enabled: bool = False
    cell_urls: str = ""  # JSON dict: {"ap-south-1": "https://ap-south-1.trustshield.io", ...}

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }


# ---------------------------------------------------------------------------
# Hydrate secrets from AWS Secrets Manager before Settings() is created.
# Reads SECRETS_MANAGER_PREFIX directly from os.environ to avoid bootstrap paradox.
# ---------------------------------------------------------------------------
try:
    from app.services.security.secrets_loader import _maybe_hydrate_secrets
    _maybe_hydrate_secrets()
except Exception:
    pass  # Secrets hydration is optional; proceed without it

# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------
settings = Settings()

# Warn on insecure defaults in non-dev environments
if settings.environment != "development":
    if not settings.jwt_secret or len(settings.jwt_secret) < 32:
        warnings.warn(
            "JWT_SECRET is empty or too short in non-development mode. "
            "Generate one with: openssl rand -hex 32",
            stacklevel=1,
        )
    if not settings.pii_encryption_key:
        warnings.warn(
            "PII_ENCRYPTION_KEY is empty in non-development mode.",
            stacklevel=1,
        )

# ---------------------------------------------------------------------------
# Convenience constants for backward compatibility
# ---------------------------------------------------------------------------
DATABASE_URL = settings.database_url
REDIS_URL = settings.redis_url
NEO4J_URI = settings.neo4j_uri
NEO4J_USER = settings.neo4j_user
NEO4J_PASSWORD = settings.neo4j_password
KAFKA_BOOTSTRAP_SERVERS = settings.kafka_bootstrap_servers
