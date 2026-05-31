"""Comprehensive API endpoint tests."""

import pytest
from tests.conftest import (
    client,
    sample_chat_request,
    sample_high_risk_request,
    sample_low_risk_request,
    sample_report_request,
    sample_webhook_request,
)


class TestAnalyzeEndpoint:
    """Tests for POST /api/v1/analyze."""

    def test_analyze_chat_success(self, client, sample_chat_request):
        """Successful chat analysis returns all required fields."""
        response = client.post("/api/v1/analyze", json=sample_chat_request)
        assert response.status_code == 200
        data = response.json()
        assert data["session_id"] == "test-session-123"
        assert "risk_score" in data
        assert "risk_level" in data
        assert data["risk_level"] in ["LOW", "MEDIUM", "HIGH", "CRITICAL"]
        assert "recommended_action" in data
        assert "flagged_entities" in data
        assert "intervention_type" in data

    def test_analyze_high_risk(self, client, sample_high_risk_request):
        """High-risk chat with OTP keywords and AnyDesk gets flagged."""
        response = client.post("/api/v1/analyze", json=sample_high_risk_request)
        assert response.status_code == 200
        data = response.json()
        assert data["risk_score"] > 50
        assert data["risk_level"] in ["HIGH", "CRITICAL"]

    def test_analyze_low_risk(self, client, sample_low_risk_request):
        """Legitimate chat gets low risk score."""
        response = client.post("/api/v1/analyze", json=sample_low_risk_request)
        assert response.status_code == 200
        data = response.json()
        assert data["risk_score"] < 30
        assert data["risk_level"] == "LOW"
        assert data["recommended_action"] == "NONE"

    def test_analyze_empty_messages(self, client):
        """Empty messages list returns 422 validation error."""
        request = {
            "messages": [],
            "session_metadata": {
                "client_app_id": "test-app",
                "session_id": "test-session-empty",
                "contact_initiated_by": "unknown",
                "is_during_active_upi_session": False,
                "user_device_hash": "abc123def456",
            },
        }
        response = client.post("/api/v1/analyze", json=request)
        assert response.status_code == 422

    def test_analyze_missing_session_metadata(self, client):
        """Missing session_metadata returns 422."""
        request = {
            "messages": [{"sender": "user", "text": "hello"}],
        }
        response = client.post("/api/v1/analyze", json=request)
        assert response.status_code == 422

    def test_analyze_with_session_timestamp(self, client):
        """Session with explicit timestamp computes duration correctly."""
        request = {
            "messages": [
                {"sender": "agent", "text": "Please share your OTP"},
            ],
            "session_metadata": {
                "client_app_id": "test-app",
                "session_id": "test-session-ts",
                "contact_initiated_by": "unknown",
                "is_during_active_upi_session": False,
                "user_device_hash": "abc123def456",
                "prior_reports_for_sender": 0,
                "session_started_at": "2026-01-01T00:00:00Z",
            },
        }
        response = client.post("/api/v1/analyze", json=request)
        assert response.status_code == 200
        data = response.json()
        assert "risk_score" in data

    def test_analyze_entity_extraction(self, client):
        """UPI IDs and phone numbers are extracted from text."""
        request = {
            "messages": [
                {
                    "sender": "agent",
                    "text": "Send money to user@okaxis or call 9876543210",
                },
            ],
            "session_metadata": {
                "client_app_id": "test-app",
                "session_id": "test-session-entities",
                "contact_initiated_by": "unknown",
                "is_during_active_upi_session": False,
                "user_device_hash": "abc123def456",
            },
        }
        response = client.post("/api/v1/analyze", json=request)
        assert response.status_code == 200
        data = response.json()
        entity_types = [e["entity_type"] for e in data["flagged_entities"]]
        assert "UPI" in entity_types


class TestWebhookEndpoint:
    """Tests for POST /api/v1/webhook/pre-transaction."""

    def test_webhook_low_risk(self, client, sample_webhook_request):
        """Low-risk transaction gets PASS."""
        response = client.post(
            "/api/v1/webhook/pre-transaction", json=sample_webhook_request
        )
        assert response.status_code == 200
        data = response.json()
        assert data["decision"] in ["PASS", "REVIEW", "BLOCK"]
        assert "risk_score" in data
        assert "risk_level" in data

    def test_webhook_high_amount(self, client):
        """High transaction amount triggers higher risk."""
        request = {
            "payer_vpa": "user@okaxis",
            "payee_vpa": "merchant@ybl",
            "amount": 100000,
            "device_fingerprint": "abc123def456",
        }
        response = client.post("/api/v1/webhook/pre-transaction", json=request)
        assert response.status_code == 200
        data = response.json()
        assert data["risk_score"] >= 30

    def test_webhook_self_transfer(self, client):
        """Self-transfer gets highest risk."""
        request = {
            "payer_vpa": "user@okaxis",
            "payee_vpa": "user@okaxis",
            "amount": 1000,
        }
        response = client.post("/api/v1/webhook/pre-transaction", json=request)
        assert response.status_code == 200
        data = response.json()
        assert data["risk_score"] >= 50
        assert "Self-transfer" in data["reason"]


class TestReportEndpoint:
    """Tests for POST /api/v1/report."""

    def test_report_entity_success(self, client, sample_report_request):
        """Successful entity report returns report_id and status."""
        response = client.post("/api/v1/report", json=sample_report_request)
        assert response.status_code == 200
        data = response.json()
        assert "report_id" in data
        assert data["status"] == "pending"
        assert "1 report(s)" in data["message"]

    def test_report_entity_confirmed_after_three(self, client, sample_report_request):
        """Entity becomes 'confirmed' after 3 reports."""
        for _ in range(3):
            client.post("/api/v1/report", json=sample_report_request)
        response = client.post("/api/v1/report", json=sample_report_request)
        data = response.json()
        assert data["status"] == "confirmed"

    def test_report_missing_entity_value(self, client):
        """Missing entity_value returns 422."""
        response = client.post(
            "/api/v1/report",
            json={"entity_type": "PHONE", "scam_type": "vishing"},
        )
        assert response.status_code == 422


class TestLookupEndpoint:
    """Tests for GET /api/v1/lookup/{entity_type}/{entity_value}."""

    def test_lookup_unknown_entity(self, client):
        """Unknown entity returns low risk."""
        response = client.get("/api/v1/lookup/PHONE/+919999999999")
        assert response.status_code == 200
        data = response.json()
        assert data["is_flagged"] is False
        assert data["report_count"] == 0
        assert data["risk_level"] == "low"

    def test_lookup_reported_entity(self, client, sample_report_request):
        """Reported entity shows correct report count."""
        client.post("/api/v1/report", json=sample_report_request)
        response = client.get(
            f"/api/v1/lookup/{sample_report_request['entity_type']}"
            f"/{sample_report_request['entity_value']}"
        )
        assert response.status_code == 200
        data = response.json()
        assert data["report_count"] == 1
        assert data["is_flagged"] is False


class TestReportStats:
    """Tests for GET /api/v1/reports/stats."""

    def test_stats_empty(self, client):
        """Stats with no reports."""
        response = client.get("/api/v1/reports/stats")
        assert response.status_code == 200
        data = response.json()
        assert data["total_entities_reported"] >= 0

    def test_stats_after_reports(self, client, sample_report_request):
        """Stats update after reporting entities."""
        client.post("/api/v1/report", json=sample_report_request)
        response = client.get("/api/v1/reports/stats")
        data = response.json()
        assert data["total_reports"] >= 1


class TestHealthAndRoot:
    """Tests for /health and / endpoints."""

    def test_health_check(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"

    def test_root_endpoint(self, client):
        response = client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "TrustShield API"
        assert data["version"] == "1.0.0"
        assert "docs" in data
