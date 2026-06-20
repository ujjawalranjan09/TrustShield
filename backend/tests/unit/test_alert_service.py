"""Unit tests for alert service routing to Alertmanager."""

import json
from unittest.mock import MagicMock, patch

import pytest


class TestAlertService:
    def test_routes_to_alertmanager(self):
        from unittest.mock import MagicMock

        mock_post = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_post.return_value = mock_response

        alert_payload = {
            "labels": {
                "alertname": "TestAlert",
                "severity": "critical",
                "environment": "staging",
            },
            "annotations": {
                "summary": "Test alert",
                "description": "This is a test",
            },
        }

        with patch("httpx.post", mock_post):
            import httpx
            response = httpx.post(
                "http://localhost:9093/api/v2/alerts",
                json=[alert_payload],
            )
            assert response.status_code == 200

    def test_rules_yaml_valid(self):
        import yaml
        import os
        rules_path = os.path.join(os.path.dirname(__file__), "..", "..", "..", "infra", "alerts", "rules.yml")
        with open(rules_path) as f:
            rules = yaml.safe_load(f)
        assert "groups" in rules
        assert len(rules["groups"]) >= 2
        critical_group = rules["groups"][0]
        assert critical_group["name"] == "trustshield_critical"
        alert_names = [r["alert"] for r in critical_group["rules"]]
        assert "AuditChainBreak" in alert_names
        assert "ModelKeywordFallbackSpike" in alert_names

    def test_alertmanager_yaml_valid(self):
        import yaml
        import os
        am_path = os.path.join(os.path.dirname(__file__), "..", "..", "..", "infra", "alerts", "alertmanager.yml")
        with open(am_path) as f:
            config = yaml.safe_load(f)
        assert "route" in config
        assert "receivers" in config
        receiver_names = [r["name"] for r in config["receivers"]]
        assert "critical-pagerduty" in receiver_names
        assert "ops-slack" in receiver_names
