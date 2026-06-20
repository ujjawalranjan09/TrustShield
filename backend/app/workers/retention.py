"""Retention enforcement — TTL cleanup jobs for data lifecycle."""

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, text

from app.config import settings
from app.database import SessionLocal

logger = logging.getLogger(__name__)


def cleanup_scan_events():
    """Delete scan_events older than retention_scan_events_days (default 730 days)."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=settings.retention_scan_events_days)
    with SessionLocal() as db:
        result = db.execute(
            delete(text("scan_events")).where(text(f"created_at < '{cutoff.isoformat()}'"))
        )
        deleted = result.rowcount
        db.commit()
        logger.info("Retention: deleted %d scan_events older than %d days", deleted, settings.retention_scan_events_days)
        return deleted


def cleanup_behavioral_signals():
    """Delete behavioral_signals older than 180 days."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=180)
    with SessionLocal() as db:
        result = db.execute(
            delete(text("behavioral_signals")).where(text(f"created_at < '{cutoff.isoformat()}'"))
        )
        deleted = result.rowcount
        db.commit()
        logger.info("Retention: deleted %d behavioral_signals older than 180 days", deleted)
        return deleted


def cleanup_feedback_labels():
    """Delete feedback_labels older than 730 days."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=settings.retention_scan_events_days)
    with SessionLocal() as db:
        result = db.execute(
            delete(text("feedback_labels")).where(text(f"created_at < '{cutoff.isoformat()}'"))
        )
        deleted = result.rowcount
        db.commit()
        logger.info("Retention: deleted %d feedback_labels older than %d days", deleted, settings.retention_scan_events_days)
        return deleted


# Note: recovery_cases (7 years) and audit_logs (indefinite) are NOT deleted.
# This is documented in the retention policy.
