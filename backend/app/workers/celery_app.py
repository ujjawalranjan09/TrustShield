"""Celery application configuration for TrustShield.

Configures the Celery worker, beat schedule, and task routing.
"""

from celery import Celery
from celery.schedules import crontab

from app.config import settings

celery_app = Celery(
    "trustshield",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=[
        "app.services.graph.risk_propagation",
        "app.services.graph.ring_detection",
        "app.services.intel.threat_ingest",
        "app.workers.tasks.billing_tasks",
        "app.workers.tasks.ml_tasks",
        "app.workers.tasks.compliance_tasks",
        "app.workers.tasks.intel_tasks",
        "app.workers.tasks.reputation_tasks",
    ],
)

# ---------------------------------------------------------------------------
# Beat schedule
# ---------------------------------------------------------------------------

celery_app.conf.beat_schedule = {
    # Existing graph tasks
    "propagate-risk-every-6-hours": {
        "task": "app.services.graph.risk_propagation.propagate_risk_scores",
        "schedule": 21600.0,
    },
    "detect-fraud-rings-every-12-hours": {
        "task": "app.services.graph.ring_detection.detect_fraud_rings",
        "schedule": 43200.0,
    },
    "ingest-threat-intel-daily": {
        "task": "app.services.intel.threat_ingest.ingest_threat_intel",
        "schedule": 86400.0,
    },
    # Billing tasks
    "nightly-usage-rollup": {
        "task": "billing.nightly_rollup",
        "schedule": crontab(minute=5, hour=0),
    },
    "stripe-metering": {
        "task": "billing.submit_stripe_metering",
        "schedule": crontab(minute=30, hour=0),
    },
    "usage-retention": {
        "task": "billing.purge_old_usage_events",
        "schedule": crontab(minute=0, hour=3, day_of_week=0),
    },
    # ML tasks
    "drift-check": {
        "task": "ml.run_drift_check",
        "schedule": crontab(minute=0, hour=1),
    },
    # Compliance tasks
    "audit-verify-daily": {
        "task": "compliance.verify_audit_chain_window",
        "schedule": crontab(minute=15, hour=1),
    },
    "audit-verify-full": {
        "task": "compliance.verify_audit_chain_full",
        "schedule": crontab(minute=0, hour=4, day_of_week=0),
    },
    "backup-audit": {
        "task": "compliance.verify_backups",
        "schedule": crontab(minute=0, hour=5, day_of_week=1),
    },
    # Reputation
    "reputation-refresh": {
        "task": "app.workers.tasks.reputation_tasks.reputation_refresh",
        "schedule": crontab(minute=0, hour=6),
    },
}

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

celery_app.conf.timezone = "Asia/Kolkata"
celery_app.conf.task_default_queue = "trustshield-default"
celery_app.conf.task_always_eager = settings.celery_task_eager
