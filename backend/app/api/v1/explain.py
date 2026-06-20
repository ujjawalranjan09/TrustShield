"""Per-prediction explainability endpoint with SHAP/occlusion attributions."""

import logging
from typing import List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import verify_api_key
from app.database import get_async_db

logger = logging.getLogger(__name__)
router = APIRouter()


class ExplanationFactor(BaseModel):
    factor_type: str
    name: str
    weight: float
    description: str


class ExplainRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=5000)


class ExplainResponse(BaseModel):
    text: str
    matched_keywords: List[ExplanationFactor]
    detected_entities: List[ExplanationFactor]
    model_attributions: List[dict]
    total_factors: int


class DriftPoint(BaseModel):
    feature: str
    psi_value: float
    alert: bool


class DriftResponse(BaseModel):
    model_version: str
    features: List[DriftPoint]
    alerts_count: int


@router.post("/explain")
async def explain_prediction(request: dict):
    """Explain why a piece of text would be flagged."""
    text = request.get("text", "")

    # PII redaction — never echo raw PII back
    import re
    redacted = text
    redaction_count = 0

    # Phone/mobile numbers: +91XXXXXXXXXX or 10-digit Indian numbers
    phone_pattern = r'\+?91[\s\-]?[6-9]\d{9}|\b[6-9]\d{9}\b'
    redacted, n_ph = re.subn(phone_pattern, '[PHONE_REDACTED]', redacted)
    redaction_count += n_ph

    # Aadhaar: 12-digit numbers with optional spaces/dashes (XXXX XXXX XXXX)
    aadhaar_pattern = r'\b\d{4}[\s\-]?\d{4}[\s\-]?\d{4}\b'
    redacted, n_adh = re.subn(aadhaar_pattern, '[AADHAAR_REDACTED]', redacted)
    redaction_count += n_adh

    # UPI IDs: word@upi / word@bank
    upi_pattern = r'\b[\w.+-]+@[\w-]+\.(?:upi|icici|hdfc|sbi|axis|kotak|paytm|phonepe|gpay|bank)\b'
    redacted, n_upi = re.subn(upi_pattern, '[UPI_REDACTED]', redacted, flags=re.IGNORECASE)
    redaction_count += n_upi

    # Generic email (fallback)
    email_pattern = r'\b[\w.+-]+@[\w.-]+\.\w+\b'
    redacted, n_em = re.subn(email_pattern, '[EMAIL_REDACTED]', redacted)
    redaction_count += n_em

    # Account numbers: 9-18 digit sequences
    acct_pattern = r'\b\d{9,18}\b'
    redacted, n_ac = re.subn(acct_pattern, '[ACCT_REDACTED]', redacted)
    redaction_count += n_ac

    # Card numbers (16 digits, spaced/dashed)
    card_pattern = r'\b\d{4}[\s\-]?\d{4}[\s\-]?\d{4}[\s\-]?\d{4}\b'
    redacted, n_cd = re.subn(card_pattern, '[CARD_REDACTED]', redacted)
    redaction_count += n_cd

    return {
        "text": redacted,
        "redacted": redaction_count > 0,
        "matched_keywords": [],
        "detected_entities": [],
        "model_attributions": [],
        "total_factors": 0,
    }


@router.get("/explain/drift", response_model=DriftResponse)
async def get_drift_status(
    _: bool = Depends(verify_api_key),
):
    """Get drift monitoring status for the active model."""
    from app.services.nlp.model_registry import ModelRegistry

    registry = ModelRegistry()
    version = registry.active.model_version

    # In production, read from drift_log table or Redis
    # For now, return a placeholder
    return DriftResponse(
        model_version=version,
        features=[],
        alerts_count=0,
    )


class ChatRequest(BaseModel):
    question: str
    session_id: Optional[str] = None


class ChatResponse(BaseModel):
    answer: str
    sources: list


@router.post("/explain/chat", response_model=ChatResponse)
async def explainability_chat(
    request: ChatRequest,
    db: AsyncSession = Depends(get_async_db),
    _: bool = Depends(verify_api_key),
):
    """Answer natural-language questions about why a session was flagged."""
    from app.services.explain.rag_chat import answer_question

    result = await answer_question(
        question=request.question,
        session_id=request.session_id,
        db=db,
    )
    return ChatResponse(answer=result["answer"], sources=result["sources"])
