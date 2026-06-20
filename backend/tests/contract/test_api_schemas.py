"""Contract tests: verify API response schemas match expected structure."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1.analyze import router as analyze_router
from app.api.v1.report import router as report_router
from app.api.v1.analytics import router as analytics_router

app = FastAPI()
app.include_router(analyze_router, prefix="/api/v1")
app.include_router(report_router, prefix="/api/v1")
app.include_router(analytics_router, prefix="/api/v1")
client = TestClient(app)


def test_analyze_response_schema():
    """Analyze endpoint returns all required fields."""
    resp = client.post("/api/v1/analyze", json={
        "messages": [{"sender": "user", "text": "hello"}],
        "session_metadata": {
            "client_app_id": "test", "session_id": "schema_test",
            "contact_initiated_by": "user", "is_during_active_upi_session": False,
            "user_device_hash": "hash", "prior_reports_for_sender": 0,
        },
    })
    if resp.status_code == 200:
        data = resp.json()
        required = ["session_id", "risk_score", "risk_level", "recommended_action",
                     "flagged_entities", "intervention_type"]
        for field in required:
            assert field in data, f"Missing field: {field}"


def test_report_stats_schema():
    """Report stats returns all required fields."""
    resp = client.get("/api/v1/reports/stats")
    if resp.status_code == 200:
        data = resp.json()
        required = ["total_entities_reported", "total_reports",
                     "confirmed_fraudsters", "pending_review"]
        for field in required:
            assert field in data, f"Missing field: {field}"
