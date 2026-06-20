"""1930 Cybercrime.gov.in submission sandbox.

Mock implementation for development. Toggle to real API via config.
"""

import logging
import uuid
from datetime import datetime

from app.config import settings

logger = logging.getLogger(__name__)


def submit_to_cybercrime(
    case_id: str,
    fraud_type: str,
    amount_lost: float,
    victim_name: str,
    victim_phone: str,
    incident_date: str,
    description: str = "",
) -> dict:
    """Submit a complaint to cybercrime.gov.in (sandbox or real).

    Returns:
        Dict with reference_number, status, and message.
    """
    if settings.cybercrime_api_url == "sandbox":
        return _sandbox_submit(case_id, fraud_type, amount_lost)
    else:
        return _real_submit(case_id, fraud_type, amount_lost, victim_name,
                           victim_phone, incident_date, description)


def _sandbox_submit(case_id: str, fraud_type: str, amount_lost: float) -> dict:
    """Mock submission for development."""
    ref_number = f"CYB-{datetime.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"
    logger.info("Sandbox 1930 submission: case=%s ref=%s", case_id[:8], ref_number)
    return {
        "reference_number": ref_number,
        "status": "submitted",
        "message": "Complaint submitted to 1930 (sandbox mode). "
                   "In production, this would be filed at cybercrime.gov.in.",
        "estimated_processing_time": "7-10 business days",
    }


def _real_submit(case_id: str, fraud_type: str, amount_lost: float,
                 victim_name: str, victim_phone: str, incident_date: str,
                 description: str) -> dict:
    """Real submission to cybercrime.gov.in API.

    TODO: Implement when the real API is available.
    Currently falls back to sandbox.
    """
    logger.warning("Real 1930 API not implemented, falling back to sandbox")
    return _sandbox_submit(case_id, fraud_type, amount_lost)
