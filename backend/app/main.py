"""TrustShield FastAPI application entry point.

Configures CORS, logging, rate limiting, request-id middleware, and mounts
all API routers.
"""

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.config import settings
from app.errors import AppError
from app.middleware.request_id import RequestIDFormatter, RequestIDMiddleware
from app.middleware.tenant_context import TenantContextMiddleware
from app.middleware.cell_router import CellRoutingMiddleware

# ---------------------------------------------------------------------------
# Sentry (env-gated)
# ---------------------------------------------------------------------------

if settings.sentry_dsn:
    import sentry_sdk
    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.environment,
        traces_sample_rate=0.1,
    )

from app.api.v1.analyze import router as analyze_router
from app.api.v1.report import router as report_router
from app.api.v1.analytics import router as analytics_router
from app.api.v1.scan import router as scan_router
from app.api.v1.image_analysis import router as image_router
from app.api.v1.behavioral import router as behavioral_router
from app.api.v1.hotspots import router as hotspots_router
from app.api.v1.intel import router as intel_router
from app.api.v1.voice import router as voice_router
from app.api.v1.recovery import router as recovery_router
from app.api.v1.auth import router as auth_router
from app.api.v1.feedback import router as feedback_router
from app.api.v1.batch import router as batch_router
from app.api.v1.explain import router as explain_router
from app.api.v1.ws_dashboard import router as ws_router
from app.api.v1.graph import router as graph_router
from app.api.v1.audit import router as audit_router
from app.api.v1.dpdp import router as dpdp_router
from app.api.v1.intervention import router as intervention_router
from app.api.v1.reputation import router as reputation_router
from app.api.v1.consumer import router as consumer_router
from app.api.v1.whatsapp import router as whatsapp_router
from app.api.v1.banker import router as banker_router
from app.api.v1.billing import router as billing_router
from app.api.v1.compliance import router as compliance_router
from app.api.v1.webhook_subscriptions import router as webhook_router
from app.api.v1.tenant import router as tenant_router
from app.api.v1.scim import router as scim_router
from app.api.v1.embed import router as embed_router
from app.api.v1.sandbox import router as sandbox_router
from app.api.v1.governance import router as governance_router
from app.services.auth.sso_router import router as sso_router
from app.middleware.audit import AuditMiddleware

# ---------------------------------------------------------------------------
# Logging – configure the root logger with the RequestIDFormatter so every
# log line includes ``request_id``.
# ---------------------------------------------------------------------------

_root_handler = logging.StreamHandler()
_root_handler.setFormatter(
    RequestIDFormatter(
        fmt="%(asctime)s - %(name)s - [%(request_id)s] - %(levelname)s - %(message)s"
    )
)
logging.root.handlers = [_root_handler]
logging.root.setLevel(getattr(logging, settings.log_level.upper(), logging.INFO))

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Rate limiter
# ---------------------------------------------------------------------------

limiter = Limiter(key_func=get_remote_address)

# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan: startup and shutdown events."""
    from pathlib import Path
    from alembic.config import Config
    from alembic import command

    # Register Prometheus counters
    from prometheus_client import Counter, Gauge, Histogram
    billing_quota_denied = Counter(
        "billing_quota_denied_total", "Billing quota denial count by plan", ["plan", "tenant_id"]
    )
    model_fallback = Counter(
        "model_fallback_total", "Model fallback count by tier", ["tier"]
    )
    audit_chain_break = Counter(
        "audit_chain_break_total", "Audit chain break count", []
    )
    pii_decrypt_total = Counter(
        "pii_decrypt_total", "PII decryption operation count", []
    )
    stripe_webhook_total = Counter(
        "stripe_webhook_total", "Stripe webhook events by type", ["event_type"]
    )
    # Phase D observability metrics
    graph_write_total = Counter(
        "graph_write_total", "Graph write operation count", ["result"]
    )
    graph_backlog_depth = Gauge(
        "graph_backlog_depth", "Number of events buffered in graph backlog"
    )
    ring_detected_total = Counter(
        "ring_detected_total", "Fraud ring detection count"
    )
    llm_call_total = Counter(
        "llm_call_total", "LLM call count", ["provider", "result"]
    )
    llm_latency_seconds = Histogram(
        "llm_latency_seconds", "LLM call latency in seconds"
    )
    intervention_enqueued_total = Counter(
        "intervention_enqueued_total", "Intervention enqueued count", ["type"]
    )
    intervention_sent_total = Counter(
        "intervention_sent_total", "Intervention sent count", ["type", "result", "tenant_id"]
    )
    reputation_lookup_total = Counter(
        "reputation_lookup_total", "Reputation lookup count", ["tier", "tenant_id"]
    )
    # Phase E observability metrics
    sso_login_total = Counter(
        "sso_login_total", "SSO login attempts by IdP and result", ["idp", "result"]
    )
    scim_request_total = Counter(
        "scim_request_total", "SCIM API requests by operation and result", ["op", "result"]
    )
    webhook_dispatch_total = Counter(
        "webhook_dispatch_total", "Outbound webhook dispatch count by result", ["result"]
    )
    webhook_retry_total = Counter(
        "webhook_retry_total", "Outbound webhook retry count"
    )
    permission_denied_total = Counter(
        "permission_denied_total", "Permission denied count by permission", ["permission"]
    )

    # Store on app state for use in routes
    app.state.counters = {
        "billing_quota_denied": billing_quota_denied,
        "model_fallback": model_fallback,
        "audit_chain_break": audit_chain_break,
        "pii_decrypt_total": pii_decrypt_total,
        "stripe_webhook_total": stripe_webhook_total,
        "graph_write_total": graph_write_total,
        "graph_backlog_depth": graph_backlog_depth,
        "ring_detected_total": ring_detected_total,
        "llm_call_total": llm_call_total,
        "llm_latency_seconds": llm_latency_seconds,
        "intervention_enqueued_total": intervention_enqueued_total,
        "intervention_sent_total": intervention_sent_total,
        "reputation_lookup_total": reputation_lookup_total,
        "sso_login_total": sso_login_total,
        "scim_request_total": scim_request_total,
        "webhook_dispatch_total": webhook_dispatch_total,
        "webhook_retry_total": webhook_retry_total,
        "permission_denied_total": permission_denied_total,
    }
    logger.info("Prometheus counters registered")

    logger.info("Starting TrustShield API (env=%s)", settings.environment)

    # Validate secrets are not defaults in production
    if settings.environment != "development":
        if not settings.jwt_secret or len(settings.jwt_secret) < 32:
            logger.critical("JWT_SECRET must be set and >= 32 chars in non-development environments")
            raise SystemExit(1)
        if settings.billing_enabled and not settings.stripe_secret_key:
            logger.critical("STRIPE_SECRET_KEY must be set when billing_enabled=True in non-development environments")
            raise SystemExit(1)
        if not settings.pii_encryption_key and not settings.kms_key_id:
            logger.critical(
                "Either PII_ENCRYPTION_KEY or KMS_KEY_ID must be set in non-development environments "
                "(victim PII would otherwise be stored in plaintext)"
            )
            raise SystemExit(1)
        if not settings.database_url.startswith("postgresql+asyncpg://"):
            logger.critical("Non-dev must use postgresql+asyncpg")
            raise SystemExit(1)
        if (
            settings.db_ssl_required
            and "sslmode" not in settings.database_url
            and "ssl=require" not in settings.database_url
        ):
            logger.critical("DB connection must require SSL in non-dev")
            raise SystemExit(1)
        if settings.event_backend == "redis" and not settings.redis_url.startswith("rediss://"):
            logger.critical("Redis must use TLS (rediss://) in non-dev")
            raise SystemExit(1)

    # Install tenant query filter
    try:
        from app.services.tenant.query_filter import install_query_filter
        install_query_filter()
        logger.info("Tenant query filter installed")
    except Exception as exc:
        logger.warning("Failed to install tenant query filter: %s", exc)

    # Register transparent field-level encryption for PII models.
    # Safe to call unconditionally — listeners are no-ops when no key is set.
    try:
        from app.services.security.encryption_listeners import (
            register_default_encrypted_fields,
        )
        register_default_encrypted_fields()
    except Exception as exc:
        logger.warning("Failed to register PII encryption listeners: %s", exc)

    # Run Alembic migrations as the source of truth
    alembic_cfg = Path(__file__).resolve().parent.parent / "alembic.ini"
    if alembic_cfg.exists():
        config = Config(str(alembic_cfg))
        try:
            command.upgrade(config, "head")
            logger.info("Database migrations applied (alembic upgrade head)")
        except Exception as exc:
            logger.error("Alembic migration failed: %s", exc)
            if settings.environment != "development":
                raise
            logger.warning("Falling back to create_all in development mode")
            from app.database import init_db
            init_db()
    else:
        logger.warning("alembic.ini not found, falling back to create_all")
        from app.database import init_db
        init_db()

    # Warm up connection pool
    from app.database import async_engine
    try:
        async with async_engine.connect() as conn:
            await conn.execute(__import__("sqlalchemy").text("SELECT 1"))
        logger.info("Database connection pool warmed up")
    except Exception as exc:
        logger.warning("Connection pool warmup failed: %s", exc)

    yield
    logger.info("Shutting down TrustShield API")
    await async_engine.dispose()


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(
    title=settings.app_name,
    description="Real-time AI-powered fraud detection platform for UPI and digital payments",
    version=settings.app_version,
    lifespan=lifespan,
)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# ---------------------------------------------------------------------------
# OpenTelemetry instrumentation
# ---------------------------------------------------------------------------

try:
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

    provider = TracerProvider()
    processor = BatchSpanProcessor(
        OTLPSpanExporter(endpoint=f"{settings.otel_endpoint}/v1/traces")
    )
    provider.add_span_processor(processor)
    trace.set_tracer_provider(provider)
    FastAPIInstrumentor.instrument_app(app)
    logger.info("OpenTelemetry instrumentation enabled (endpoint=%s)", settings.otel_endpoint)
except Exception as exc:
    logger.warning("OpenTelemetry instrumentation disabled: %s", exc)

# ---------------------------------------------------------------------------
# Prometheus /metrics endpoint
# ---------------------------------------------------------------------------

try:
    from prometheus_client import make_asgi_app
    metrics_app = make_asgi_app()
    app.mount("/metrics", metrics_app)
except Exception as exc:
    logger.warning("Prometheus metrics endpoint disabled: %s", exc)

# Request-ID middleware (added before CORS so the ID is available early)
app.add_middleware(RequestIDMiddleware)
app.add_middleware(TenantContextMiddleware)
app.add_middleware(CellRoutingMiddleware)

# CORS middleware
allowed_origins = [origin.strip() for origin in settings.allowed_origins.split(",")]
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

# Audit middleware (after CORS, before request handling)
app.add_middleware(AuditMiddleware)


# ---------------------------------------------------------------------------
# Global exception handler
# ---------------------------------------------------------------------------


@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    """Handle application-specific errors with consistent envelope."""
    trace_id = getattr(request.state, "request_id", None)
    content = {
        "error": exc.__class__.__name__,
        "detail": exc.detail,
        "code": exc.code,
        "trace_id": trace_id,
    }
    if exc.extra:
        content["extra"] = exc.extra
    return JSONResponse(status_code=exc.status_code, content=content)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catch-all exception handler for unhandled errors."""
    logger.error("Unhandled exception: %s", exc, exc_info=True)
    trace_id = getattr(request.state, "request_id", None)
    return JSONResponse(
        status_code=500,
        content={
            "error": "InternalServerError",
            "detail": "An unexpected error occurred. Please try again later.",
            "code": "INTERNAL_ERROR",
            "trace_id": trace_id,
        },
    )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.get("/")
@limiter.exempt
async def root() -> dict:
    """Root endpoint with API information."""
    return {
        "message": settings.app_name,
        "version": settings.app_version,
        "status": "running",
        "docs": "/docs",
    }


@app.get("/health")
@limiter.exempt
async def health() -> dict:
    """Health check endpoint with actual DB connectivity probe."""
    from app.database import async_engine
    from sqlalchemy import text

    db_ok = False
    try:
        async with async_engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        db_ok = True
    except Exception as exc:
        logger.warning("Health check – DB probe failed: %s", exc)

    status_code = 200 if db_ok else 503
    from starlette.responses import JSONResponse as _JR

    return _JR(
        status_code=status_code,
        content={
            "status": "healthy" if db_ok else "degraded",
            "database": "connected" if db_ok else "unavailable",
        },
    )


# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------

app.include_router(analyze_router, prefix="/api/v1", tags=["Analysis"])
app.include_router(report_router, prefix="/api/v1", tags=["Reports"])
app.include_router(analytics_router, prefix="/api/v1", tags=["Analytics"])
app.include_router(scan_router, prefix="/api/v1", tags=["Scanner"])
app.include_router(image_router, prefix="/api/v1", tags=["Image Analysis"])
app.include_router(behavioral_router, prefix="/api/v1", tags=["Behavioral"])
app.include_router(hotspots_router, prefix="/api/v1", tags=["Hotspots"])
app.include_router(intel_router, prefix="/api/v1", tags=["Intelligence Network"])
app.include_router(voice_router, prefix="/api/v1", tags=["Voice Analysis"])
app.include_router(recovery_router, prefix="/api/v1", tags=["Recovery"])
app.include_router(auth_router, prefix="/api/v1", tags=["Authentication"])
app.include_router(feedback_router, prefix="/api/v1", tags=["Feedback"])
app.include_router(batch_router, prefix="/api/v1", tags=["Batch Analysis"])
app.include_router(explain_router, prefix="/api/v1", tags=["Explainability"])
app.include_router(ws_router, prefix="/api/v1", tags=["WebSocket"])
app.include_router(graph_router, prefix="/api/v1", tags=["Graph"])
app.include_router(audit_router, prefix="/api/v1", tags=["Audit"])
app.include_router(dpdp_router, prefix="/api/v1", tags=["DPDP"])
app.include_router(intervention_router, prefix="/api/v1", tags=["Intervention"])
app.include_router(reputation_router, prefix="/api/v1", tags=["Reputation"])
app.include_router(consumer_router, prefix="/api/v1", tags=["Consumer"])
app.include_router(whatsapp_router, prefix="/api/v1", tags=["WhatsApp"])
app.include_router(banker_router, prefix="/api/v1", tags=["Banker Dashboard"])
app.include_router(billing_router, prefix="/api/v1", tags=["Billing"])
app.include_router(compliance_router, prefix="/api/v1", tags=["Compliance"])
app.include_router(webhook_router, prefix="/api/v1", tags=["Webhooks"])
app.include_router(tenant_router, prefix="/api/v1", tags=["Tenant"])
app.include_router(sso_router, prefix="/api/v1", tags=["SSO"])
app.include_router(scim_router, prefix="/api/v1", tags=["SCIM"])
app.include_router(embed_router, prefix="/api/v1", tags=["Embed"])
app.include_router(sandbox_router, prefix="/api/v1", tags=["Sandbox"])
app.include_router(governance_router, prefix="/api/v1", tags=["Governance"])
