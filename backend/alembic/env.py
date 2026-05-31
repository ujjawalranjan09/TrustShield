"""Alembic environment configuration.

Reads DATABASE_URL from the app's pydantic-settings config and
uses the shared Base metadata for autogenerate support.
"""

import sys
from logging.config import fileConfig
from pathlib import Path

from sqlalchemy import engine_from_config, pool

from alembic import context

# Ensure app package is importable
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import DATABASE_URL
from app.database import Base

# Import all models so Base.metadata knows about them
from app.models.session import FraudSession, RiskEvent  # noqa: F401
from app.models.entity import FlaggedEntity  # noqa: F401

# Alembic Config object
config = context.config

# Override sqlalchemy.url from app config
config.set_main_option("sqlalchemy.url", DATABASE_URL)

# Logging
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Target metadata for autogenerate
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (generates SQL without connecting)."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode (connects to database)."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
