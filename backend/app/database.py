"""Database configuration for TrustShield.

Provides both async engine (for FastAPI runtime) and sync engine (for Alembic).
"""

from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.pool import QueuePool

from app.config import settings

# ---------------------------------------------------------------------------
# Async engine (FastAPI runtime)
# ---------------------------------------------------------------------------

if settings.database_url.startswith("sqlite"):
    DATABASE_URL_ASYNC = settings.database_url.replace("sqlite:///", "sqlite+aiosqlite:///")
else:
    DATABASE_URL_ASYNC = settings.database_url.replace("postgresql://", "postgresql+asyncpg://")

_engine_kwargs = dict(
    pool_size=settings.db_pool_size,
    max_overflow=settings.db_max_overflow,
    pool_timeout=settings.db_pool_timeout,
    pool_recycle=settings.db_pool_recycle,
    pool_pre_ping=True,
)

# Inject SSL for asyncpg when required (non-dev environments)
if (
    settings.db_ssl_required
    and settings.environment != "development"
    and not settings.database_url.startswith("sqlite")
):
    _engine_kwargs["connect_args"] = {"ssl": "require"}

async_engine = create_async_engine(DATABASE_URL_ASYNC, **_engine_kwargs)

AsyncSessionLocal = async_sessionmaker(
    async_engine, class_=AsyncSession, expire_on_commit=False
)

# ---------------------------------------------------------------------------
# Sync engine (Alembic migrations)
# ---------------------------------------------------------------------------

sync_engine = create_engine(
    settings.database_url,
    poolclass=QueuePool,
    pool_size=settings.db_pool_size,
    max_overflow=settings.db_max_overflow,
    pool_timeout=settings.db_pool_timeout,
    pool_recycle=settings.db_pool_recycle,
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=sync_engine)

# ---------------------------------------------------------------------------
# Base class for models
# ---------------------------------------------------------------------------

Base = declarative_base()

# ---------------------------------------------------------------------------
# Dependencies
# ---------------------------------------------------------------------------


async def get_async_db():
    """Async dependency for FastAPI endpoints."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


def get_db():
    """Sync dependency (kept for Alembic env.py and legacy code)."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Table initialization (kept for backward compat; prefer Alembic)
# ---------------------------------------------------------------------------


def init_db():
    """Initialize database tables using sync engine."""
    from app.models.tenant import Tenant  # noqa: F401
    from app.models.user import User  # noqa: F401
    from app.models.intel import Bank, SharedEntity, CrossBankReport  # noqa: F401
    from app.models.recovery import RecoveryCase  # noqa: F401
    from app.models.scan_event import ScanEvent  # noqa: F401
    from app.models.audit import AuditLog  # noqa: F401
    from app.models.feedback import FeedbackLabel  # noqa: F401
    from app.models.session import FraudSession, RiskEvent, RevokedSession  # noqa: F401
    from app.models.refresh_token import RefreshToken  # noqa: F401
    from app.models.shadow_prediction import ShadowPrediction  # noqa: F401
    from app.models.billing import Plan, Subscription, UsageLedger, UsageEvent  # noqa: F401
    from app.models.sso import SSOConfig  # noqa: F401
    from app.services.integration.webhook_dispatcher import WebhookSubscription  # noqa: F401
    from app.services.governance.change_mgmt import ChangeRecord  # noqa: F401
    from app.models.auth import Role, UserRole  # noqa: F401
    from app.models.compliance import DataAsset  # noqa: F401

    Base.metadata.create_all(bind=sync_engine)
