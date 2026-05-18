import pytest
import asyncio
from fastapi.testclient import TestClient
from app.api.v1.analyze import router
from fastapi import FastAPI

app = FastAPI()
app.include_router(router, prefix="/v1")

client = TestClient(app)

def test_analyze_legitimate():
    payload = {
        "messages": [
            {"sender": "user", "text": "Hi, what is the status of my order?"},
            {"sender": "agent", "text": "It will be delivered tomorrow."}
        ],
        "session_metadata": {
            "client_app_id": "app_1",
            "session_id": "sess_1",
            "contact_initiated_by": "user",
            "is_during_active_upi_session": False,
            "user_device_hash": "hash1",
            "prior_reports_for_sender": 0
        }
    }

    response = client.post("/v1/analyze", json=payload)
    assert response.status_code == 200
    data = response.json()

    # As we have a mocked classifier that uses randomness,
    # we assert the endpoint processes it successfully without error.
    assert "risk_score" in data
    assert "risk_level" in data
    assert "recommended_action" in data
    assert data["session_id"] == "sess_1"

def test_analyze_scam_anydesk():
    payload = {
        "messages": [
            {"sender": "agent", "text": "Please share your AnyDesk ID 123456789 to process refund."}
        ],
        "session_metadata": {
            "client_app_id": "app_2",
            "session_id": "sess_2",
            "contact_initiated_by": "unknown",
            "is_during_active_upi_session": True,
            "user_device_hash": "hash2",
            "prior_reports_for_sender": 2
        }
    }

    response = client.post("/v1/analyze", json=payload)
    assert response.status_code == 200
    data = response.json()

    # Asserting AnyDesk entity is caught
    entities = [e["entity_type"] for e in data["flagged_entities"]]
    assert "ANYDESK" in entities

    # Expected high/critical risk due to AnyDesk, contact initiated by unknown, and active UPI session
    assert data["risk_score"] > 50
    assert data["recommended_action"] in ["HARD_BLOCK", "FREEZE_AND_REPORT", "CRITICAL_REPORT"]
