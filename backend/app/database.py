from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.pool import QueuePool
from app.config import DATABASE_URL

# Create engine with connection pooling
engine = create_engine(
    DATABASE_URL,
    poolclass=QueuePool,
    pool_size=5,
    max_overflow=10,
    pool_pre_ping=True,
    pool_recycle=300,
)

# Session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base class for models
Base = declarative_base()


def get_db():
    """Dependency for FastAPI endpoints that need database access."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Initialize database tables."""
    from app.models.session import FraudSession, RiskEvent
    from app.models.entity import FlaggedEntity

    Base.metadata.create_all(bind=engine)
