"""Shared pytest fixtures for the TrustShield test suite."""

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client() -> TestClient:
    """Create a test client for the FastAPI app."""
    return TestClient(app)


@pytest.fixture
def sample_chat_request() -> dict:
    """Sample medium-risk chat analysis request."""
    return {
        "messages": [
            {
                "sender": "agent",
                "text": "Hello sir, I am calling from bank. aapka debit card block ho gaya hai.",
            },
            {"sender": "user", "text": "what? why?"},
            {
                "sender": "agent",
                "text": "bhai apna OTP batao verify karne ke liye, phir unblock hoga.",
            },
        ],
        "session_metadata": {
            "client_app_id": "test-app",
            "session_id": "test-session-123",
            "contact_initiated_by": "unknown",
            "is_during_active_upi_session": False,
            "user_device_hash": "abc123def456",
            "prior_reports_for_sender": 0,
        },
    }


@pytest.fixture
def sample_high_risk_request() -> dict:
    """High-risk chat request with multiple scam indicators."""
    return {
        "messages": [
            {
                "sender": "agent",
                "text": "Please share your OTP immediately and download AnyDesk app for remote access.",
            },
        ],
        "session_metadata": {
            "client_app_id": "test-app",
            "session_id": "test-session-high-risk",
            "contact_initiated_by": "unknown",
            "is_during_active_upi_session": True,
            "user_device_hash": "def456ghi789",
            "prior_reports_for_sender": 5,
        },
    }


@pytest.fixture
def sample_low_risk_request() -> dict:
    """Low-risk legitimate chat request."""
    return {
        "messages": [
            {"sender": "user", "text": "Hi, when will my order be delivered?"},
            {
                "sender": "agent",
                "text": "Your order will be delivered by tomorrow 8 PM.",
            },
        ],
        "session_metadata": {
            "client_app_id": "test-app",
            "session_id": "test-session-low-risk",
            "contact_initiated_by": "known",
            "is_during_active_upi_session": False,
            "user_device_hash": "abc123def456",
            "prior_reports_for_sender": 0,
        },
    }


@pytest.fixture
def sample_report_request() -> dict:
    """Sample entity report request."""
    return {
        "entity_value": "+91 98765 43210",
        "entity_type": "PHONE",
        "scam_type": "vishing",
        "description": "Called claiming to be from bank, asked for OTP",
    }


@pytest.fixture
def sample_webhook_request() -> dict:
    """Sample pre-transaction webhook request."""
    return {
        "payer_vpa": "user@okaxis",
        "payee_vpa": "merchant@ybl",
        "amount": 50000,
        "device_fingerprint": "abc123def456",
    }
