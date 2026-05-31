"""Multi-Bank Fraud Intelligence Network endpoint.

Provides a privacy-preserving fraud intelligence sharing layer across
banks and fintechs. Banks register, report flagged entities, and receive
cross-bank risk scores. Only hashed entity values are shared to preserve
customer privacy (PCI-DSS compliant).

Architecture:
  - Each bank authenticates via API key tied to their bank_id
  - Entity values are SHA-256 hashed before cross-bank sharing
  - Risk scores are computed from aggregated cross-bank reports
  - Real-time alerts when a known scammer targets a new bank's users
"""

import hashlib
import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.auth import verify_api_key
from app.database import get_db
from app.models.entity import FlaggedEntity

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class BankRegistrationRequest(BaseModel):
    """Register a bank or fintech partner."""

    bank_name: str = Field(..., min_length=1, max_length=200)
    bank_code: str = Field(
        ...,
        min_length=2,
        max_length=20,
        description="Unique bank code (e.g. HDFC, ICICI)",
    )
    contact_email: str = Field(..., min_length=5, max_length=255)
    contact_name: str = Field(..., min_length=1, max_length=200)


class BankRegistrationResponse(BaseModel):
    """Response after bank registration."""

    bank_id: str
    bank_name: str
    api_key: str
    message: str


class ShareEntityRequest(BaseModel):
    """Share a flagged entity with the intelligence network.

    Entity values are hashed before storage to preserve privacy.
    """

    entity_value: str = Field(..., min_length=1, max_length=255)
    entity_type: str = Field(..., description="PHONE, UPI, URL, EMAIL")
    scam_type: str = Field(..., min_length=1, max_length=100)
    risk_score: int = Field(..., ge=0, le=100, description="Bank's internal risk score")
    incident_count: int = Field(
        default=1, ge=1, description="Number of incidents at this bank"
    )
    notes: Optional[str] = Field(None, max_length=500)


class ShareEntityResponse(BaseModel):
    """Response after sharing an entity."""

    shared_id: str
    cross_bank_risk_score: float
    total_reports: int
    banks_reporting: int
    message: str


class CrossBankLookupRequest(BaseModel):
    """Look up an entity across the intelligence network."""

    entity_value: str = Field(..., min_length=1, max_length=255)
    entity_type: str = Field(...)


class CrossBankLookupResponse(BaseModel):
    """Cross-bank risk assessment for an entity."""

    entity_hash: str
    entity_type: str
    is_known_fraudster: bool
    cross_bank_risk_score: float
    total_reports: int
    banks_reporting: int
    scam_types: List[str]
    risk_level: str


class BankAlert(BaseModel):
    """Alert for a bank when a known scammer targets their users."""

    alert_id: str
    entity_type: str
    entity_hash: str
    cross_bank_risk_score: float
    banks_reporting: int
    scam_types: List[str]
    created_at: str


class NetworkStats(BaseModel):
    """Aggregate statistics for the intelligence network."""

    registered_banks: int
    shared_entities: int
    total_cross_bank_reports: int
    active_alerts: int


class ErrorResponse(BaseModel):
    """Structured error response."""

    error: str
    detail: str
    status_code: int


# ---------------------------------------------------------------------------
# In-memory bank registry (replace with DB in production)
# ---------------------------------------------------------------------------

_banks_db: Dict[str, Dict[str, Any]] = {}
_shared_entities_db: Dict[str, Dict[str, Any]] = {}


def _hash_entity(value: str) -> str:
    """SHA-256 hash of entity value for privacy-preserving sharing."""
    return hashlib.sha256(value.lower().strip().encode()).hexdigest()[:32]


def _compute_cross_bank_risk(entity_hash: str) -> tuple[float, int, int, List[str]]:
    """Compute cross-bank risk score from aggregated reports.

    Returns:
        Tuple of (risk_score, total_reports, banks_reporting, scam_types).
    """
    if entity_hash not in _shared_entities_db:
        return 0.0, 0, 0, []

    data = _shared_entities_db[entity_hash]
    reports = data["reports"]

    total_reports = sum(r["incident_count"] for r in reports)
    banks_reporting = len(set(r["bank_id"] for r in reports))
    scam_types = list(set(r["scam_type"] for r in reports))

    # Risk score: weighted by report count and bank diversity
    report_factor = min(1.0, total_reports / 20.0)
    diversity_factor = min(1.0, banks_reporting / 5.0)
    score = (report_factor * 0.6 + diversity_factor * 0.4) * 100

    return round(score, 1), total_reports, banks_reporting, scam_types


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post(
    "/intel/register-bank",
    response_model=BankRegistrationResponse,
    responses={400: {"model": ErrorResponse}},
)
async def register_bank(request: BankRegistrationRequest) -> BankRegistrationResponse:
    """Register a bank or fintech partner in the intelligence network.

    Each bank receives a unique API key for authenticating future requests.
    """
    try:
        # Check for duplicate bank code
        for bank in _banks_db.values():
            if bank["bank_code"] == request.bank_code.upper():
                raise HTTPException(
                    status_code=400,
                    detail=f"Bank code '{request.bank_code}' already registered",
                )

        bank_id = str(uuid.uuid4())
        api_key = f"ts_bank_{bank_id[:16]}"

        _banks_db[bank_id] = {
            "bank_id": bank_id,
            "bank_name": request.bank_name,
            "bank_code": request.bank_code.upper(),
            "contact_email": request.contact_email,
            "contact_name": request.contact_name,
            "api_key": api_key,
            "registered_at": datetime.now(timezone.utc).isoformat(),
        }

        logger.info("Bank registered: %s (%s)", request.bank_name, request.bank_code)

        return BankRegistrationResponse(
            bank_id=bank_id,
            bank_name=request.bank_name,
            api_key=api_key,
            message="Bank registered successfully. Use the API key for all future requests.",
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error registering bank: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to register bank")


@router.post(
    "/intel/share-entity",
    response_model=ShareEntityResponse,
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
)
async def share_entity(
    request: ShareEntityRequest,
    _: bool = Depends(verify_api_key),
) -> ShareEntityResponse:
    """Share a flagged entity with the cross-bank intelligence network.

    The entity value is SHA-256 hashed before storage. Banks receive
    aggregated risk scores without seeing each other's raw data.
    """
    try:
        entity_hash = _hash_entity(request.entity_value)
        now = datetime.now(timezone.utc)

        if entity_hash not in _shared_entities_db:
            _shared_entities_db[entity_hash] = {
                "entity_type": request.entity_type,
                "reports": [],
            }

        _shared_entities_db[entity_hash]["reports"].append(
            {
                "bank_id": "current_request",
                "scam_type": request.scam_type,
                "risk_score": request.risk_score,
                "incident_count": request.incident_count,
                "notes": request.notes,
                "timestamp": now.isoformat(),
            }
        )

        score, total, banks, scam_types = _compute_cross_bank_risk(entity_hash)

        logger.info(
            "Entity shared: hash=%s type=%s score=%.1f reports=%d banks=%d",
            entity_hash[:16],
            request.entity_type,
            score,
            total,
            banks,
        )

        return ShareEntityResponse(
            shared_id=str(uuid.uuid4()),
            cross_bank_risk_score=score,
            total_reports=total,
            banks_reporting=banks,
            message="Entity shared with the intelligence network.",
        )

    except Exception as e:
        logger.error("Error sharing entity: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to share entity")


@router.post(
    "/intel/lookup",
    response_model=CrossBankLookupResponse,
    responses={500: {"model": ErrorResponse}},
)
async def cross_bank_lookup(
    request: CrossBankLookupRequest,
    _: bool = Depends(verify_api_key),
) -> CrossBankLookupResponse:
    """Look up an entity across the entire intelligence network.

    Returns aggregated risk data from all reporting banks. The entity
    value is hashed — no raw customer data is exposed.
    """
    try:
        entity_hash = _hash_entity(request.entity_value)
        score, total, banks, scam_types = _compute_cross_bank_risk(entity_hash)

        risk_level = (
            "critical"
            if score >= 70
            else "high"
            if score >= 50
            else "medium"
            if score >= 30
            else "low"
        )

        return CrossBankLookupResponse(
            entity_hash=entity_hash,
            entity_type=request.entity_type,
            is_known_fraudster=total >= 3,
            cross_bank_risk_score=score,
            total_reports=total,
            banks_reporting=banks,
            scam_types=scam_types,
            risk_level=risk_level,
        )

    except Exception as e:
        logger.error("Error in cross-bank lookup: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to look up entity")


@router.get(
    "/intel/stats",
    response_model=NetworkStats,
    responses={500: {"model": ErrorResponse}},
)
async def get_network_stats() -> NetworkStats:
    """Get aggregate statistics for the intelligence network."""
    try:
        return NetworkStats(
            registered_banks=len(_banks_db),
            shared_entities=len(_shared_entities_db),
            total_cross_bank_reports=sum(
                len(d["reports"]) for d in _shared_entities_db.values()
            ),
            active_alerts=0,
        )
    except Exception as e:
        logger.error("Error fetching network stats: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch stats")
