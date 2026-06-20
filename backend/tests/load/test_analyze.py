"""Locust load test for TrustShield — three weighted user classes.

Profile: 60% analyze, 30% webhook, 10% batch.

Usage:
    locust -f tests/load/test_analyze.py --host=http://localhost:8000
    locust -f tests/load/test_analyze.py --host=https://api.trustshield.example.com \
        --headless -u 500 -r 50 --run-time 5m
"""

from uuid import uuid4

from locust import HttpUser, between, task
import random


# ---------------------------------------------------------------------------
# Shared payloads
# ---------------------------------------------------------------------------

SCAM_MESSAGES = [
    "Hello sir, I am calling from bank. Your account is blocked. Share your OTP.",
    "Aapka refund approved hai. QR code scan karo aur PIN enter karo.",
    "AnyDesk download karo for remote support. Code batao: 123456789.",
    "Your account has been compromised. Verify immediately with your Aadhaar.",
    "Share your OTP to activate the new SIM card for Jio.",
    "KYC update karna hai. Link click karo aur details bhejo.",
]

BENIGN_MESSAGES = [
    "Hi, when will my order be delivered?",
    "Meeting tomorrow at 3pm. Don't be late.",
    "Payment received. Thank you for your purchase.",
    "Can you send me the invoice for last month?",
    "Happy birthday! Wishing you a great year ahead.",
]

ALL_MESSAGES = SCAM_MESSAGES + BENIGN_MESSAGES


def _session_id() -> str:
    return f"load-{uuid4()}"


def _analyze_payload() -> dict:
    return {
        "messages": [{"sender": "user", "text": random.choice(ALL_MESSAGES)}],
        "session_metadata": {
            "client_app_id": "loadtest",
            "session_id": _session_id(),
            "contact_initiated_by": "unknown",
            "is_during_active_upi_session": random.choice([True, False]),
            "user_device_hash": f"loadtest-{random.randint(1, 500)}",
            "prior_reports_for_sender": random.randint(0, 5),
        },
    }


def _webhook_payload() -> dict:
    return {
        "payer_vpa": f"payer{random.randint(1, 5000)}@okicici",
        "payee_vpa": f"payee{random.randint(1, 5000)}@okaxis",
        "amount": round(random.uniform(10, 200000), 2),
        "note": random.choice(["groceries", "rent", "salary", "gift", ""]),
        "transaction_id": f"TXN{random.randint(10**9, 10**10 - 1)}",
    }


def _batch_payload(n: int = 5) -> dict:
    return {
        "items": [
            {
                "messages": [{"sender": "user", "text": random.choice(ALL_MESSAGES)}],
                "session_metadata": {
                    "client_app_id": "loadtest",
                    "session_id": _session_id(),
                    "contact_initiated_by": "unknown",
                    "is_during_active_upi_session": False,
                    "user_device_hash": "loadtest-batch",
                    "prior_reports_for_sender": 0,
                },
            }
            for _ in range(n)
        ]
    }


BANK_API_KEY = "test-key"


# ---------------------------------------------------------------------------
# User classes
# ---------------------------------------------------------------------------


class AnalyzeUser(HttpUser):
    """60 % of traffic — single-message analyze requests."""

    weight = 60
    wait_time = between(0.1, 0.4)

    @task
    def analyze(self):
        self.client.post(
            "/api/v1/analyze",
            json=_analyze_payload(),
            headers={"X-API-Key": BANK_API_KEY},
            name="/api/v1/analyze [single]",
        )


class WebhookUser(HttpUser):
    """30 % of traffic — pre-transaction webhook calls."""

    weight = 30
    wait_time = between(0.05, 0.2)

    @task
    def pre_transaction(self):
        self.client.post(
            "/api/v1/webhook/pre-transaction",
            json=_webhook_payload(),
            headers={"X-API-Key": BANK_API_KEY},
            name="/api/v1/webhook/pre-transaction",
        )


class BatchUser(HttpUser):
    """10 % of traffic — batch analyze (5 items per request)."""

    weight = 10
    wait_time = between(0.3, 1.0)

    @task
    def batch_analyze(self):
        self.client.post(
            "/api/v1/analyze/batch",
            json=_batch_payload(5),
            headers={"X-API-Key": BANK_API_KEY},
            name="/api/v1/analyze/batch",
        )
