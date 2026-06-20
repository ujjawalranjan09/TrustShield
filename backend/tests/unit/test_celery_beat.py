"""Unit tests for Celery beat schedule configuration."""

import pytest


class TestCeleryBeatSchedule:
    def test_beat_schedule_has_all_tasks(self):
        from app.workers.celery_app import celery_app

        expected_tasks = [
            "nightly-usage-rollup",
            "stripe-metering",
            "usage-retention",
            "drift-check",
            "audit-verify-daily",
            "audit-verify-full",
            "backup-audit",
        ]
        schedule = celery_app.conf.beat_schedule
        for task_name in expected_tasks:
            assert task_name in schedule, f"Missing task: {task_name}"

    def test_nightly_rollup_schedule(self):
        from app.workers.celery_app import celery_app

        task = celery_app.conf.beat_schedule["nightly-usage-rollup"]
        assert task["task"] == "billing.nightly_rollup"
        schedule = task["schedule"]
        assert 5 in schedule.minute
        assert 0 in schedule.hour

    def test_stripe_metering_schedule(self):
        from app.workers.celery_app import celery_app

        task = celery_app.conf.beat_schedule["stripe-metering"]
        assert task["task"] == "billing.submit_stripe_metering"
        schedule = task["schedule"]
        assert 30 in schedule.minute
        assert 0 in schedule.hour

    def test_usage_retention_weekly(self):
        from app.workers.celery_app import celery_app

        task = celery_app.conf.beat_schedule["usage-retention"]
        schedule = task["schedule"]
        assert 0 in schedule.hour or 3 in schedule.hour
        assert 0 in schedule.day_of_week

    def test_drift_check_daily(self):
        from app.workers.celery_app import celery_app

        task = celery_app.conf.beat_schedule["drift-check"]
        assert task["task"] == "ml.run_drift_check"
        schedule = task["schedule"]
        assert 0 in schedule.minute
        assert 1 in schedule.hour

    def test_audit_verify_daily(self):
        from app.workers.celery_app import celery_app

        task = celery_app.conf.beat_schedule["audit-verify-daily"]
        schedule = task["schedule"]
        assert 1 in schedule.hour
        assert 15 in schedule.minute

    def test_backup_audit_weekly(self):
        from app.workers.celery_app import celery_app

        task = celery_app.conf.beat_schedule["backup-audit"]
        schedule = task["schedule"]
        assert 0 in schedule.hour or 5 in schedule.hour
        assert 1 in schedule.day_of_week

    def test_task_default_queue(self):
        from app.workers.celery_app import celery_app

        assert celery_app.conf.task_default_queue == "trustshield-default"

    def test_includes_task_modules(self):
        from app.workers.celery_app import celery_app

        includes = celery_app.conf.include
        assert "app.workers.tasks.billing_tasks" in includes
        assert "app.workers.tasks.ml_tasks" in includes
        assert "app.workers.tasks.compliance_tasks" in includes
