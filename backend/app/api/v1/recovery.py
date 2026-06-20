"""Victim Recovery Assistant endpoint — DB-backed."""

import json
import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_async_db
from app.models.recovery import RecoveryCase
from app.schemas.recovery import (
    ComplaintDraft,
    FraudType,
    RecoveryPlan,
    RecoveryRequest,
    RecoveryStep,
    RecoveryStatusResponse,
    RecoveryStatusUpdate,
)

logger = logging.getLogger(__name__)
router = APIRouter()

# Backward-compatible re-exports
FraudType = FraudType
RecoveryRequest = RecoveryRequest
RecoveryStep = RecoveryStep
ComplaintDraft = ComplaintDraft
RecoveryPlan = RecoveryPlan
RecoveryStatusResponse = RecoveryStatusResponse
RecoveryStatusUpdate = RecoveryStatusUpdate


RECOVERY_STEPS = {
    "vishing": [
        {"title": "Block Your Bank Card", "description": "Call your bank helpline or use mobile app to block your card immediately.", "is_urgent": True, "estimated_time": "5 minutes"},
        {"title": "File Complaint on Cybercrime.gov.in", "description": "File online at cybercrime.gov.in or call 1930 helpline.", "action_url": "https://cybercrime.gov.in", "action_label": "File Complaint", "is_urgent": True, "estimated_time": "15 minutes"},
        {"title": "Report to Your Bank", "description": "Visit branch or call customer care. Request chargeback.", "is_urgent": True, "estimated_time": "30 minutes"},
        {"title": "Change All Passwords", "description": "Change passwords for banking apps, email. Enable 2FA.", "estimated_time": "20 minutes"},
        {"title": "File an FIR", "description": "Visit nearest police station or file e-FIR online.", "estimated_time": "1 hour"},
        {"title": "Monitor Your Account", "description": "Set up transaction alerts. Check daily for 30 days.", "estimated_time": "Ongoing"},
    ],
    "upi_fraud": [
        {"title": "Raise Dispute in UPI App", "description": "Open UPI app, raise transaction dispute immediately.", "is_urgent": True, "estimated_time": "5 minutes"},
        {"title": "Block UPI on Your Account", "description": "Disable UPI through bank app or customer care.", "is_urgent": True, "estimated_time": "5 minutes"},
        {"title": "File Complaint on Cybercrime.gov.in", "description": "File at cybercrime.gov.in or call 1930. Mention UTR number.", "action_url": "https://cybercrime.gov.in", "action_label": "File Complaint", "is_urgent": True, "estimated_time": "15 minutes"},
        {"title": "Report to NPCI", "description": "Email od@npci.org.in with transaction details.", "action_url": "mailto:od@npci.org.in", "action_label": "Email NPCI", "estimated_time": "10 minutes"},
        {"title": "Visit Bank Branch", "description": "Visit with cybercrime complaint and ID proof.", "estimated_time": "1 hour"},
        {"title": "Monitor for 60 Days", "description": "NPCI dispute takes up to 45 days. Follow up weekly.", "estimated_time": "Ongoing"},
    ],
    "remote_access": [
        {"title": "Uninstall Remote Access App", "description": "Remove AnyDesk/TeamViewer immediately.", "is_urgent": True, "estimated_time": "2 minutes"},
        {"title": "Disconnect from Internet", "description": "Turn off WiFi and mobile data.", "is_urgent": True, "estimated_time": "1 minute"},
        {"title": "Block All Cards", "description": "Call bank and block all debit/credit cards.", "is_urgent": True, "estimated_time": "5 minutes"},
        {"title": "Factory Reset Phone", "description": "If compromised, factory reset after backup.", "estimated_time": "30 minutes"},
        {"title": "File Cybercrime Complaint", "description": "File at cybercrime.gov.in or call 1930.", "action_url": "https://cybercrime.gov.in", "action_label": "File Complaint", "is_urgent": True, "estimated_time": "15 minutes"},
    ],
    "qr_code_fraud": [
        {"title": "Check Transaction Status", "description": "Verify if payment was actually debited.", "is_urgent": True, "estimated_time": "2 minutes"},
        {"title": "Raise Dispute if Debited", "description": "Raise dispute in UPI app with transaction reference.", "is_urgent": True, "estimated_time": "5 minutes"},
        {"title": "File Cybercrime Complaint", "description": "File at cybercrime.gov.in or call 1930.", "action_url": "https://cybercrime.gov.in", "action_label": "File Complaint", "is_urgent": True, "estimated_time": "15 minutes"},
    ],
}
DEFAULT_STEPS = [
    {"title": "File Cybercrime Complaint", "description": "File at cybercrime.gov.in or call 1930.", "action_url": "https://cybercrime.gov.in", "action_label": "File Complaint", "is_urgent": True, "estimated_time": "15 minutes"},
    {"title": "Contact Your Bank", "description": "Report to bank fraud department.", "is_urgent": True, "estimated_time": "30 minutes"},
    {"title": "Change Passwords", "description": "Change all financial and email passwords.", "estimated_time": "20 minutes"},
    {"title": "File FIR", "description": "File police complaint.", "estimated_time": "1 hour"},
]
HELPLINES = [
    {"name": "National Cybercrime Helpline", "number": "1930", "description": "24/7 toll-free"},
    {"name": "Cybercrime Portal", "number": "cybercrime.gov.in", "description": "Online complaint filing"},
    {"name": "NPCI UPI Dispute", "number": "od@npci.org.in", "description": "Email for UPI disputes"},
    {"name": "RBI Ombudsman", "number": "14448", "description": "Banking complaint escalation"},
]


def _build_complaint(case_id, fraud_type, amount, scammer_info, date, name, phone, bank):
    title = f"Complaint regarding {fraud_type.replace('_',' ')} fraud - Case {case_id[:8].upper()}"
    body = f"""To, The Station House Officer, Cyber Crime Police Station

Subject: Complaint of {fraud_type.replace('_',' ')} fraud amounting to Rs. {amount:,.0f}

I, {name or '[YOUR NAME]'}, mobile {phone or '[YOUR PHONE]'}, report {fraud_type.replace('_',' ')} fraud.
Date: {date} | Amount: Rs. {amount:,.0f} | Bank: {bank or '[YOUR BANK]'}
Scammer: {scammer_info or 'Unknown'} | Ref: {case_id[:8].upper()}

Request investigation and appropriate action.
"""
    return ComplaintDraft(title=title, body=body, sections={
        "incident_summary": f"{fraud_type.replace('_',' ').title()} fraud of Rs. {amount:,.0f} on {date}",
        "financial_loss": f"Rs. {amount:,.0f}", "scammer_details": scammer_info or "Unknown",
        "case_reference": case_id[:8].upper(),
    })


@router.post("/recovery/initiate", response_model=RecoveryPlan, status_code=201)
async def initiate_recovery(request: RecoveryRequest, db: AsyncSession = Depends(get_async_db)):
    case_id = str(uuid.uuid4())
    step_templates = RECOVERY_STEPS.get(request.fraud_type.value, DEFAULT_STEPS)
    steps = [RecoveryStep(step_number=i+1, **t) for i, t in enumerate(step_templates)]
    complaint = _build_complaint(case_id, request.fraud_type.value, request.amount_lost,
                                  request.scammer_info, request.incident_date,
                                  request.victim_name, request.victim_phone, request.bank_name)

    case = RecoveryCase(
        case_id=case_id, fraud_type=request.fraud_type.value, amount_lost=request.amount_lost,
        scammer_info=request.scammer_info, incident_date=request.incident_date,
        victim_name=request.victim_name, victim_phone=request.victim_phone,
        bank_name=request.bank_name, upi_id=request.upi_id,
        total_steps=len(step_templates),
    )
    db.add(case)
    await db.commit()

    logger.info("Recovery initiated: case=%s type=%s", case_id[:8], request.fraud_type.value)
    return RecoveryPlan(case_id=case_id, fraud_type=request.fraud_type.value, amount_lost=request.amount_lost,
                        steps=steps, complaint_draft=complaint, helpline_numbers=HELPLINES,
                        next_deadline=datetime.now(timezone.utc).isoformat())


@router.get("/recovery/{case_id}", response_model=RecoveryStatusResponse)
async def get_recovery_case(case_id: str, db: AsyncSession = Depends(get_async_db)):
    """Get a recovery case by its ID (RESTful GET /recovery/{case_id})."""
    result = await db.execute(select(RecoveryCase).filter(RecoveryCase.case_id == case_id))
    case = result.scalars().first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    return RecoveryStatusResponse(case_id=case_id, current_step=case.current_step,
                                 total_steps=case.total_steps, status=case.status,
                                 last_updated=case.last_updated.isoformat() if case.last_updated else "")


@router.get("/recovery/{case_id}/status", response_model=RecoveryStatusResponse)
async def get_recovery_status(case_id: str, db: AsyncSession = Depends(get_async_db)):
    result = await db.execute(select(RecoveryCase).filter(RecoveryCase.case_id == case_id))
    case = result.scalars().first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    return RecoveryStatusResponse(case_id=case_id, current_step=case.current_step,
                                   total_steps=case.total_steps, status=case.status,
                                   last_updated=case.last_updated.isoformat() if case.last_updated else "")


@router.post("/recovery/{case_id}/update", response_model=RecoveryStatusResponse)
async def update_recovery_status(case_id: str, update: RecoveryStatusUpdate, db: AsyncSession = Depends(get_async_db)):
    result = await db.execute(select(RecoveryCase).filter(RecoveryCase.case_id == case_id))
    case = result.scalars().first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    case.current_step = min(update.current_step, case.total_steps)
    case.last_updated = datetime.now(timezone.utc)
    if case.current_step >= case.total_steps:
        case.status = "completed"
    await db.commit()
    return RecoveryStatusResponse(case_id=case_id, current_step=case.current_step,
                                   total_steps=case.total_steps, status=case.status,
                                   last_updated=case.last_updated.isoformat())


@router.patch("/recovery/{case_id}", response_model=RecoveryStatusResponse)
async def patch_recovery_status(case_id: str, update: RecoveryStatusUpdate, db: AsyncSession = Depends(get_async_db)):
    """PATCH alias for RESTful semantics (backward-compatible with POST)."""
    return await update_recovery_status(case_id, update, db)


@router.get("/recovery/{case_id}/complaint-draft")
async def get_complaint_draft(case_id: str, db: AsyncSession = Depends(get_async_db)):
    """Return structured complaint draft JSON."""
    result = await db.execute(select(RecoveryCase).filter(RecoveryCase.case_id == case_id))
    case = result.scalars().first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    title = f"Complaint regarding {case.fraud_type.replace('_', ' ')} fraud - Case {case_id[:8].upper()}"
    body = f"""To, The Station House Officer, Cyber Crime Police Station

Subject: Complaint of {case.fraud_type.replace('_', ' ')} fraud amounting to Rs. {case.amount_lost:,.0f}

I, {case.victim_name or '[YOUR NAME]'}, mobile {case.victim_phone or '[YOUR PHONE]'}, report {case.fraud_type.replace('_', ' ')} fraud.
Date: {case.incident_date} | Amount: Rs. {case.amount_lost:,.0f} | Bank: {case.bank_name or '[YOUR BANK]'}
Scammer: {case.scammer_info or 'Unknown'} | Ref: {case_id[:8].upper()}

Request investigation and appropriate action.
"""
    return {
        "case_id": case_id,
        "title": title,
        "body": body,
        "sections": {
            "incident_summary": f"{case.fraud_type.replace('_', ' ').title()} fraud of Rs. {case.amount_lost:,.0f} on {case.incident_date}",
            "financial_loss": f"Rs. {case.amount_lost:,.0f}",
            "scammer_details": case.scammer_info or "Unknown",
            "case_reference": case_id[:8].upper(),
        },
    }


@router.get("/recovery/{case_id}/complaint-pdf")
async def download_complaint_pdf(case_id: str, db: AsyncSession = Depends(get_async_db)):
    """Generate and download complaint PDF."""
    from fastapi.responses import StreamingResponse
    from app.services.complaint_pdf import generate_complaint_pdf

    result = await db.execute(select(RecoveryCase).filter(RecoveryCase.case_id == case_id))
    case = result.scalars().first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    pdf_bytes = generate_complaint_pdf(
        case_id=case.case_id,
        fraud_type=case.fraud_type,
        amount_lost=case.amount_lost,
        incident_date=case.incident_date,
        victim_name=case.victim_name or "",
        victim_phone=case.victim_phone or "",
        bank_name=case.bank_name or "",
        scammer_info=case.scammer_info or "",
    )

    return StreamingResponse(
        iter([pdf_bytes]),
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=complaint-{case_id[:8]}.pdf"},
    )


@router.post("/recovery/{case_id}/submit-1930")
async def submit_to_1930(case_id: str, db: AsyncSession = Depends(get_async_db)):
    """Submit complaint to 1930 cybercrime portal and persist receipt."""
    from app.services.compliance.cybercrime_sandbox import submit_to_cybercrime

    result = await db.execute(select(RecoveryCase).filter(RecoveryCase.case_id == case_id))
    case = result.scalars().first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    submission = submit_to_cybercrime(
        case_id=case.case_id,
        fraud_type=case.fraud_type,
        amount_lost=case.amount_lost,
        victim_name=case.victim_name or "",
        victim_phone=case.victim_phone or "",
        incident_date=case.incident_date,
    )

    # Persist the receipt onto the RecoveryCase (B3.3)
    import json
    case.cybercrime_ref_number = submission.get("reference_number")
    case.cybercrime_submitted_at = datetime.now(timezone.utc)
    case.cybercrime_submission_receipt = json.dumps(submission)
    case.cybercrime_status = "submitted"
    await db.commit()

    return {"case_id": case_id, **submission}


@router.get("/recovery/{case_id}/submission-receipt")
async def get_submission_receipt(case_id: str, db: AsyncSession = Depends(get_async_db)):
    """Get the cybercrime submission receipt for a recovery case."""
    result = await db.execute(select(RecoveryCase).filter(RecoveryCase.case_id == case_id))
    case = result.scalars().first()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    if case.cybercrime_status == "not_submitted":
        raise HTTPException(
            status_code=404,
            detail="No cybercrime submission found for this case. "
                   "Submit via POST /recovery/{case_id}/submit-1930 first.",
        )

    return {
        "case_id": case_id,
        "cybercrime_ref_number": case.cybercrime_ref_number,
        "cybercrime_submitted_at": case.cybercrime_submitted_at.isoformat() if case.cybercrime_submitted_at else None,
        "cybercrime_status": case.cybercrime_status,
        "submission_receipt": json.loads(case.cybercrime_submission_receipt) if case.cybercrime_submission_receipt else None,
    }
