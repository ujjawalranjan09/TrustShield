"""Victim Recovery Assistant endpoint.

Guides fraud victims through the recovery process after a scam:
- Step-by-step recovery workflow
- Auto-generated complaint drafts for cybercrime.gov.in
- 1930 helpline integration
- Recovery status tracking
- Nearest cyber cell lookup

This is a differentiator — most fraud platforms focus on prevention
but ignore the aftermath.
"""

import logging
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.auth import verify_api_key

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class FraudType(str, Enum):
    """Types of fraud the victim experienced."""

    VISHING = "vishing"
    UPI_FRAUD = "upi_fraud"
    SIM_SWAP = "sim_swap"
    QR_CODE_FRAUD = "qr_code_fraud"
    REMOTE_ACCESS = "remote_access"
    IDENTITY_THEFT = "identity_theft"
    PHISHING = "phishing"
    OTHER = "other"


class RecoveryRequest(BaseModel):
    """Initiate a recovery workflow after being scammed."""

    fraud_type: FraudType
    amount_lost: float = Field(..., ge=0, description="Amount lost in INR")
    scammer_info: Optional[str] = Field(None, max_length=500, description="Phone/UPI/URL of scammer")
    incident_date: str = Field(..., description="ISO-8601 date of the incident")
    victim_name: Optional[str] = Field(None, max_length=200)
    victim_phone: Optional[str] = Field(None, max_length=15)
    bank_name: Optional[str] = Field(None, max_length=200)
    upi_id: Optional[str] = Field(None, max_length=255)


class RecoveryStep(BaseModel):
    """A single step in the recovery process."""

    step_number: int
    title: str
    description: str
    action_url: Optional[str] = None
    action_label: Optional[str] = None
    is_urgent: bool = False
    estimated_time: Optional[str] = None


class ComplaintDraft(BaseModel):
    """Auto-generated complaint draft for filing."""

    title: str
    body: str
    sections: Dict[str, str]


class RecoveryPlan(BaseModel):
    """Full recovery plan for the victim."""

    case_id: str
    fraud_type: str
    amount_lost: float
    steps: List[RecoveryStep]
    complaint_draft: ComplaintDraft
    helpline_numbers: List[Dict[str, str]]
    next_deadline: Optional[str] = None


class RecoveryStatusUpdate(BaseModel):
    """Update the status of a recovery case."""

    case_id: str
    current_step: int
    notes: Optional[str] = None


class RecoveryStatusResponse(BaseModel):
    """Current status of a recovery case."""

    case_id: str
    current_step: int
    total_steps: int
    status: str  # 'in_progress', 'completed', 'escalated'
    last_updated: str


class ErrorResponse(BaseModel):
    error: str
    detail: str
    status_code: int


# ---------------------------------------------------------------------------
# In-memory case store (replace with DB in production)
# ---------------------------------------------------------------------------

_cases_db: Dict[str, Dict[str, Any]] = {}


# ---------------------------------------------------------------------------
# Recovery step templates
# ---------------------------------------------------------------------------

RECOVERY_STEPS: Dict[str, List[Dict[str, Any]]] = {
    "vishing": [
        {"title": "Block Your Bank Card", "description": "Immediately call your bank's helpline or use the mobile app to block your debit/credit card. This prevents further unauthorized transactions.", "action_url": None, "is_urgent": True, "estimated_time": "5 minutes"},
        {"title": "File a Complaint on Cybercrime.gov.in", "description": "File an online complaint at cybercrime.gov.in or call the 1930 helpline. Keep your complaint number safe.", "action_url": "https://cybercrime.gov.in", "action_label": "File Complaint", "is_urgent": True, "estimated_time": "15 minutes"},
        {"title": "Report to Your Bank", "description": "Visit your bank branch or call customer care. Request a chargeback for any unauthorized transactions. Provide the cybercrime complaint number.", "is_urgent": True, "estimated_time": "30 minutes"},
        {"title": "Change All Passwords", "description": "Change passwords for your banking apps, email, and any other apps that share the same password. Enable 2FA everywhere.", "estimated_time": "20 minutes"},
        {"title": "File an FIR", "description": "Visit your nearest police station or file an e-FIR online. Carry the cybercrime complaint printout and bank statements.", "action_url": None, "estimated_time": "1 hour"},
        {"title": "Monitor Your Account", "description": "Set up transaction alerts via SMS and email. Check your account daily for the next 30 days for any unauthorized activity.", "estimated_time": "Ongoing"},
    ],
    "upi_fraud": [
        {"title": "Raise Dispute in UPI App", "description": "Open your UPI app (Google Pay, PhonePe, Paytm) and raise a transaction dispute immediately. Select the fraudulent transaction and click 'Report Issue'.", "is_urgent": True, "estimated_time": "5 minutes"},
        {"title": "Block UPI on Your Account", "description": "Temporarily disable UPI through your bank's app or by calling customer care to prevent further unauthorized transactions.", "is_urgent": True, "estimated_time": "5 minutes"},
        {"title": "File Complaint on Cybercrime.gov.in", "description": "File a complaint at cybercrime.gov.in or call 1930. Mention the UPI transaction reference number (UTR).", "action_url": "https://cybercrime.gov.in", "action_label": "File Complaint", "is_urgent": True, "estimated_time": "15 minutes"},
        {"title": "Report to NPCI", "description": "Email the NPCI dispute resolution team at od@npci.org.in with transaction details and complaint number.", "action_url": "mailto:od@npci.org.in", "action_label": "Email NPCI", "estimated_time": "10 minutes"},
        {"title": "Visit Bank Branch", "description": "Visit your bank with the cybercrime complaint, transaction details, and ID proof. Request formal chargeback.", "estimated_time": "1 hour"},
        {"title": "Monitor for 60 Days", "description": "NPCI dispute resolution takes up to 45 days. Monitor your account and follow up weekly.", "estimated_time": "Ongoing"},
    ],
    "remote_access": [
        {"title": "Uninstall Remote Access App", "description": "Immediately uninstall AnyDesk, TeamViewer, or any remote access app the scammer asked you to install.", "is_urgent": True, "estimated_time": "2 minutes"},
        {"title": "Disconnect from Internet", "description": "Turn off WiFi and mobile data to prevent the scammer from accessing your device remotely.", "is_urgent": True, "estimated_time": "1 minute"},
        {"title": "Block All Cards via Bank", "description": "Call your bank immediately and block all debit/credit cards. The scammer may have accessed your banking apps.", "is_urgent": True, "estimated_time": "5 minutes"},
        {"title": "Factory Reset Phone (if compromised)", "description": "If the scammer had full access, factory reset your phone after backing up essential data. This removes any malware.", "estimated_time": "30 minutes"},
        {"title": "File Cybercrime Complaint", "description": "File at cybercrime.gov.in or call 1930. Mention that remote access was granted.", "action_url": "https://cybercrime.gov.in", "action_label": "File Complaint", "is_urgent": True, "estimated_time": "15 minutes"},
    ],
    "qr_code_fraud": [
        {"title": "Check Transaction Status", "description": "Open your UPI app and check if the payment was actually debited. Sometimes QR scams show fake confirmation screens.", "is_urgent": True, "estimated_time": "2 minutes"},
        {"title": "Raise Dispute if Debited", "description": "If money was debited, raise a dispute in the UPI app immediately with the transaction reference.", "is_urgent": True, "estimated_time": "5 minutes"},
        {"title": "File Cybercrime Complaint", "description": "File at cybercrime.gov.in or call 1930 with the transaction details.", "action_url": "https://cybercrime.gov.in", "action_label": "File Complaint", "is_urgent": True, "estimated_time": "15 minutes"},
    ],
}

DEFAULT_RECOVERY_STEPS = [
    {"title": "File Cybercrime Complaint", "description": "File at cybercrime.gov.in or call 1930 helpline immediately.", "action_url": "https://cybercrime.gov.in", "action_label": "File Complaint", "is_urgent": True, "estimated_time": "15 minutes"},
    {"title": "Contact Your Bank", "description": "Report the incident to your bank's fraud department.", "is_urgent": True, "estimated_time": "30 minutes"},
    {"title": "Change Passwords", "description": "Change passwords for all financial and email accounts.", "estimated_time": "20 minutes"},
    {"title": "File FIR", "description": "File a police complaint at your nearest station or online.", "estimated_time": "1 hour"},
]

HELPLINE_NUMBERS = [
    {"name": "National Cybercrime Helpline", "number": "1930", "description": "24/7 toll-free"},
    {"name": "Cybercrime Portal", "number": "cybercrime.gov.in", "description": "Online complaint filing"},
    {"name": "NPCI UPI Dispute", "number": "od@npci.org.in", "description": "Email for UPI disputes"},
    {"name": "RBI Ombudsman", "number": "14448", "description": "Banking complaint escalation"},
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_complaint_draft(
    case_id: str,
    fraud_type: str,
    amount_lost: float,
    scammer_info: Optional[str],
    incident_date: str,
    victim_name: Optional[str],
    victim_phone: Optional[str],
    bank_name: Optional[str],
) -> ComplaintDraft:
    """Auto-generate a complaint draft for cybercrime.gov.in filing."""
    title = f"Complaint regarding {fraud_type.replace('_', ' ')} fraud - Case {case_id[:8].upper()}"

    body = f"""To,
The Station House Officer,
Cyber Crime Police Station

Subject: Complaint of {fraud_type.replace('_', ' ')} fraud amounting to Rs. {amount_lost:,.0f}

Respected Sir/Madam,

I, {victim_name or '[YOUR NAME]'}, bearing mobile number {victim_phone or '[YOUR PHONE]'}, wish to report a case of {fraud_type.replace('_', ' ')} fraud.

Date of Incident: {incident_date}
Amount Lost: Rs. {amount_lost:,.0f}
Bank: {bank_name or '[YOUR BANK]'}
Scammer Details: {scammer_info or 'Unknown'}
Case Reference: {case_id[:8].upper()}

The above-mentioned fraud was committed against me. I request you to kindly investigate the matter and take appropriate action.

I declare that the contents of this complaint are true and correct to the best of my knowledge.

Yours faithfully,
{victim_name or '[YOUR NAME]'}
Date: {datetime.now(timezone.utc).strftime('%Y-%m-%d')}
"""

    sections = {
        "incident_summary": f"{fraud_type.replace('_', ' ').title()} fraud of Rs. {amount_lost:,.0f} on {incident_date}",
        "financial_loss": f"Rs. {amount_lost:,.0f}",
        "scammer_details": scammer_info or "Unknown",
        "bank_name": bank_name or "Not specified",
        "case_reference": case_id[:8].upper(),
    }

    return ComplaintDraft(title=title, body=body, sections=sections)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post(
    "/recovery/initiate",
    response_model=RecoveryPlan,
    responses={500: {"model": ErrorResponse}},
)
async def initiate_recovery(
    request: RecoveryRequest,
    _: bool = Depends(verify_api_key),
) -> RecoveryPlan:
    """Initiate a recovery workflow after being scammed.

    Creates a personalized recovery plan with step-by-step instructions,
    auto-generates a complaint draft, and provides helpline numbers.
    """
    try:
        case_id = str(uuid.uuid4())

        # Get recovery steps for this fraud type
        step_templates = RECOVERY_STEPS.get(request.fraud_type.value, DEFAULT_RECOVERY_STEPS)

        steps = []
        for i, template in enumerate(step_templates, 1):
            steps.append(
                RecoveryStep(
                    step_number=i,
                    title=template["title"],
                    description=template["description"],
                    action_url=template.get("action_url"),
                    action_label=template.get("action_label"),
                    is_urgent=template.get("is_urgent", False),
                    estimated_time=template.get("estimated_time"),
                )
            )

        # Generate complaint draft
        complaint = _build_complaint_draft(
            case_id=case_id,
            fraud_type=request.fraud_type.value,
            amount_lost=request.amount_lost,
            scammer_info=request.scammer_info,
            incident_date=request.incident_date,
            victim_name=request.victim_name,
            victim_phone=request.victim_phone,
            bank_name=request.bank_name,
        )

        # Store case
        _cases_db[case_id] = {
            "case_id": case_id,
            "fraud_type": request.fraud_type.value,
            "amount_lost": request.amount_lost,
            "current_step": 1,
            "status": "in_progress",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "last_updated": datetime.now(timezone.utc).isoformat(),
        }

        # First step deadline: 24 hours for urgent steps
        next_deadline = datetime.now(timezone.utc).isoformat()

        logger.info(
            "Recovery initiated: case=%s type=%s amount=%.0f",
            case_id[:8],
            request.fraud_type.value,
            request.amount_lost,
        )

        return RecoveryPlan(
            case_id=case_id,
            fraud_type=request.fraud_type.value,
            amount_lost=request.amount_lost,
            steps=steps,
            complaint_draft=complaint,
            helpline_numbers=[
                {"name": h["name"], "number": h["number"], "description": h["description"]}
                for h in HELPLINE_NUMBERS
            ],
            next_deadline=next_deadline,
        )

    except Exception as e:
        logger.error("Error initiating recovery: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to initiate recovery")


@router.get(
    "/recovery/{case_id}/status",
    response_model=RecoveryStatusResponse,
    responses={404: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
)
async def get_recovery_status(case_id: str) -> RecoveryStatusResponse:
    """Get the current status of a recovery case."""
    if case_id not in _cases_db:
        raise HTTPException(status_code=404, detail="Case not found")

    case = _cases_db[case_id]
    fraud_type = case["fraud_type"]
    total_steps = len(RECOVERY_STEPS.get(fraud_type, DEFAULT_RECOVERY_STEPS))

    return RecoveryStatusResponse(
        case_id=case_id,
        current_step=case["current_step"],
        total_steps=total_steps,
        status=case["status"],
        last_updated=case["last_updated"],
    )


@router.post(
    "/recovery/{case_id}/update",
    response_model=RecoveryStatusResponse,
    responses={404: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
)
async def update_recovery_status(
    case_id: str,
    update: RecoveryStatusUpdate,
) -> RecoveryStatusResponse:
    """Update the status of a recovery case (mark steps as completed)."""
    if case_id not in _cases_db:
        raise HTTPException(status_code=404, detail="Case not found")

    case = _cases_db[case_id]
    fraud_type = case["fraud_type"]
    total_steps = len(RECOVERY_STEPS.get(fraud_type, DEFAULT_RECOVERY_STEPS))

    case["current_step"] = min(update.current_step, total_steps)
    case["last_updated"] = datetime.now(timezone.utc).isoformat()

    if case["current_step"] >= total_steps:
        case["status"] = "completed"

    return RecoveryStatusResponse(
        case_id=case_id,
        current_step=case["current_step"],
        total_steps=total_steps,
        status=case["status"],
        last_updated=case["last_updated"],
    )
