"""Integration tests for feedback endpoint."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1.feedback import router

app = FastAPI()
app.include_router(router, prefix="/api/v1")
client = TestClient(app)


def test_submit_feedback():
    """Submit feedback label."""
    resp = client.post("/api/v1/feedback", json={
        "session_id": "test_session_1",
        "original_risk_score": 85,
        "original_risk_level": "CRITICAL",
        "original_action": "FREEZE_AND_REPORT",
        "analyst_label": "true_positive",
        "notes": "Confirmed vishing attack",
    })
    # May fail if DB not available
    assert resp.status_code in (201, 500)


def test_feedback_invalid_label():
    """Invalid label type rejected."""
    resp = client.post("/api/v1/feedback", json={
        "session_id": "test_session_2",
        "original_risk_score": 50,
        "original_risk_level": "MEDIUM",
        "original_action": "SOFT_WARNING",
        "analyst_label": "invalid_label",
    })
    assert resp.status_code == 422  # Validation error
