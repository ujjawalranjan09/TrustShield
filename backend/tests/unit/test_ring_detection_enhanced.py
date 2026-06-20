"""Unit tests for fraud-ring detection enhancements (D1.2).

Tests config defaults and Celery task registration for intel_tasks.
"""


class TestRingDetectionConfig:
    def test_config_defaults(self):
        """Assert ring_min_entities=5, ring_min_reports=10, interval=15."""
        from app.config import settings

        assert settings.ring_min_entities == 5
        assert settings.ring_min_reports == 10
        assert settings.ring_detect_interval_minutes == 15


class TestCeleryIntelTasks:
    def test_task_registered(self):
        """Assert celery_app has the intel tasks in include list."""
        from app.workers.celery_app import celery_app

        includes = celery_app.conf.include
        assert "app.workers.tasks.intel_tasks" in includes

    def test_detect_fraud_rings_task_registered(self):
        """Assert detect_fraud_rings_task is a registered Celery task."""
        from app.workers.tasks.intel_tasks import detect_fraud_rings_task

        assert detect_fraud_rings_task.name == "app.workers.tasks.intel_tasks.detect_fraud_rings_task"

    def test_trigger_ring_check_task_registered(self):
        """Assert trigger_ring_check is a registered Celery task."""
        from app.workers.tasks.intel_tasks import trigger_ring_check

        assert trigger_ring_check.name == "app.workers.tasks.intel_tasks.trigger_ring_check"
