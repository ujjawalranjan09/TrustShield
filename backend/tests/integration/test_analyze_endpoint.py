"""Integration tests for the analyze endpoint."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1.analyze import router

app = FastAPI()
app.include_router(router, prefix="/v1")

client = TestClient(app)


def test_analyze_legitimate():
    """Legitimate conversation gets low risk."""
    payload = {
        "messages": [
            {"sender": "user", "text": "Hi, what is the status of my order?"},
            {"sender": "agent", "text": "It will be delivered tomorrow."},
        ],
        "session_metadata": {
            "client_app_id": "app_1",
            "session_id": "sess_1",
            "contact_initiated_by": "user",
            "is_during_active_upi_session": False,
            "user_device_hash": "hash1",
            "prior_reports_for_sender": 0,
        },
    }

    response = client.post("/v1/analyze", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "risk_score" in data
    assert "risk_level" in data
    assert "recommended_action" in data
    assert data["session_id"] == "sess_1"


def test_analyze_scam_anydesk():
    """AnyDesk reference triggers entity extraction and high risk."""
    payload = {
        "messages": [
            {
                "sender": "agent",
                "text": "Please share your AnyDesk ID 123456789 to process refund.",
            },
        ],
        "session_metadata": {
            "client_app_id": "app_2",
            "session_id": "sess_2",
            "contact_initiated_by": "unknown",
            "is_during_active_upi_session": True,
            "user_device_hash": "hash2",
            "prior_reports_for_sender": 2,
        },
    }

    response = client.post("/v1/analyze", json=payload)
    assert response.status_code == 200
    data = response.json()

    entities = [e["entity_type"] for e in data["flagged_entities"]]
    assert "ANYDESK" in entities
    assert data["risk_score"] > 50
    assert data["recommended_action"] in [
        "HARD_BLOCK",
        "FREEZE_AND_REPORT",
        "CRITICAL_REPORT",
    ]


def test_analyze_with_timestamp_duration():
    """Session with timestamp computes duration correctly."""
    payload = {
        "messages": [
            {"sender": "agent", "text": "Share your OTP batao"},
        ],
        "session_metadata": {
            "client_app_id": "app_3",
            "session_id": "sess_3",
            "contact_initiated_by": "unknown",
            "is_during_active_upi_session": False,
            "user_device_hash": "hash3",
            "prior_reports_for_sender": 0,
            "session_started_at": "2026-01-01T00:00:00Z",
        },
    }

    response = client.post("/v1/analyze", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["risk_score"] > 0


def test_analyze_webhook_low_risk():
    """Low-risk webhook transaction."""
    payload = {
        "payer_vpa": "user@okaxis",
        "payee_vpa": "merchant@ybl",
        "amount": 500,
    }
    response = client.post("/v1/webhook/pre-transaction", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["decision"] == "PASS"
    assert data["risk_score"] == 0


def test_analyze_webhook_self_transfer():
    """Self-transfer gets BLOCK."""
    payload = {
        "payer_vpa": "user@okaxis",
        "payee_vpa": "user@okaxis",
        "amount": 10000,
    }
    response = client.post("/v1/webhook/pre-transaction", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["decision"] == "BLOCK"
    assert data["risk_score"] >= 50
