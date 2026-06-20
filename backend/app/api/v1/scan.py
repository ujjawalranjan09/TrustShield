"""WhatsApp/Telegram Scam Scanner endpoint.

Simplified, stateless message analysis for consumer-facing bots.
Users forward suspicious messages to a TrustShield bot, and this
endpoint returns a risk assessment in <5 seconds. No session context
required — designed for one-shot message scanning.
"""

import logging
import time
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.auth import verify_api_key
from app.schemas.entity import ExtractedEntity
from app.services.nlp.risk_scorer import SessionContext

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class ScanMessageRequest(BaseModel):
    """Single message to scan for scam indicators.

    Designed for WhatsApp/Telegram bot integration where users
    forward suspicious messages for analysis.
    """

    text: str = Field(
        ...,
        min_length=1,
        max_length=5000,
        description="The message text to analyze",
    )
    language: Optional[str] = Field(
        default=None,
        description="Language hint (e.g. 'en', 'hi', 'hinglish'). Auto-detected if omitted.",
    )
    source: Optional[str] = Field(
        default=None,
        description="Source platform (e.g. 'whatsapp', 'telegram', 'sms')",
    )


class ScanResult(BaseModel):
    """Result of a single message scan."""

    is_scam: bool
    confidence: float
    scam_type: str
    risk_level: str
    risk_score: int
    flagged_entities: List[ExtractedEntity]
    warning_message_en: Optional[str] = None
    warning_message_hi: Optional[str] = None
    recommendation: str
    processing_time_ms: int


class ScanMessageResponse(BaseModel):
    """Full response for the scan-message endpoint."""

    result: ScanResult
    user_message_en: str
    user_message_hi: str


class ErrorResponse(BaseModel):
    """Structured error response."""

    error: str
    detail: str
    status_code: int


# ---------------------------------------------------------------------------
# Service instances (lazy init — no module-level singletons)
# ---------------------------------------------------------------------------

_preprocessor = None
_extractor = None
_classifier = None
_scorer = None


def _get_services():
    global _preprocessor, _extractor, _classifier, _scorer
    if _preprocessor is None:
        from app.services.nlp.preprocessor import TextPreprocessor
        from app.services.nlp.entity_extractor import EntityExtractor
        from app.services.nlp.classifier import ScamClassifier
        from app.services.nlp.risk_scorer import RiskScorer
        _preprocessor = TextPreprocessor()
        _extractor = EntityExtractor()
        _classifier = ScamClassifier()
        _scorer = RiskScorer()
    return _preprocessor, _extractor, _classifier, _scorer


# ---------------------------------------------------------------------------
# Recommendation generator
# ---------------------------------------------------------------------------


def _get_recommendation(score: int, entities: List[ExtractedEntity]) -> str:
    """Generate a human-readable recommendation based on risk score.

    Args:
        score: Risk score 0-100.
        entities: Extracted entities from the message.

    Returns:
        Recommendation string.
    """
    entity_types = {e.entity_type.value for e in entities}

    if score >= 70:
        parts = ["This message is very likely a scam."]
        if "ANYDESK" in entity_types or "TEAMVIEWER" in entity_types:
            parts.append(
                "It requests remote access software — never share screen with strangers."
            )
        if any("OTP" in str(e.value).upper() for e in entities):
            parts.append(
                "Never share your OTP with anyone, even if they claim to be from your bank."
            )
        parts.append(
            "Do NOT click any links or share personal information. Block the sender."
        )
        return " ".join(parts)
    elif score >= 40:
        return "This message shows signs of potential fraud. Be cautious — do not share OTP, PIN, or install any remote access apps."
    elif score >= 20:
        return "This message has some suspicious elements. Verify the sender's identity before taking any action."
    else:
        return "This message appears to be legitimate, but always stay vigilant."


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post(
    "/scan",
    response_model=ScanMessageResponse,
    responses={
        400: {"model": ErrorResponse, "description": "Invalid request"},
        429: {"model": ErrorResponse, "description": "Rate limit exceeded"},
        500: {"model": ErrorResponse, "description": "Internal server error"},
    },
)
async def scan_message_short(
    request: ScanMessageRequest,
    _: bool = Depends(verify_api_key),
) -> ScanMessageResponse:
    """Alias for /scan-message — scan a single message for scam indicators."""
    return await _do_scan(request)


@router.post(
    "/scan-message",
    response_model=ScanMessageResponse,
    responses={
        400: {"model": ErrorResponse, "description": "Invalid request"},
        429: {"model": ErrorResponse, "description": "Rate limit exceeded"},
        500: {"model": ErrorResponse, "description": "Internal server error"},
    },
)
async def scan_message(
    request: ScanMessageRequest,
    _: bool = Depends(verify_api_key),
) -> ScanMessageResponse:
    return await _do_scan(request)


async def _do_scan(request: ScanMessageRequest) -> ScanMessageResponse:
    """Scan a single message for scam indicators.

    Designed for WhatsApp/Telegram bot integration. Users forward
    suspicious messages and receive a risk assessment within seconds.

    The analysis is stateless — no session context is needed. The pipeline:
    1. Preprocess and clean the text
    2. Extract entities (UPI IDs, phone numbers, remote access codes)
    3. Classify using keyword matching
    4. Compute risk score
    5. Generate bilingual recommendation
    """
    start_time = time.time()
    preprocessor, extractor, classifier, scorer = _get_services()

    try:
        # 1. Preprocess
        cleaned_text = preprocessor.clean(request.text)

        # 2. Detect language if not provided
        _language = request.language or preprocessor.detect_language(cleaned_text)

        # 3. Extract entities
        entities = extractor.extract(cleaned_text)

        # 4. Classify
        classification = await classifier.classify(cleaned_text)

        # 5. Risk scoring (simplified context for standalone scan)
        context = SessionContext(
            classifier_output=classification,
            extracted_entities=entities,
            contact_initiated_by="unknown",  # Unknown sender for forwarded messages
            time_since_session_start=0,
            number_of_messages=1,
            is_during_active_upi_session=False,
            prior_reports_for_sender=0,
        )
        risk = scorer.score(context)

        # 6. Generate recommendation
        recommendation = _get_recommendation(risk.score, entities)

        processing_time_ms = max(1, int((time.time() - start_time) * 1000))

        # Determine warning messages
        # Generate adaptive warnings
        from app.services.nlp.warning_generator import WarningGenerator
        warn_gen = WarningGenerator()
        warnings = warn_gen.generate(
            scam_type=classification.scam_type.value,
            risk_score=risk.score,
            entities=entities,
        )
        warning_en = warnings["warning_en"] or None
        warning_hi = warnings["warning_hi"] or None

        logger.info(
            "Scanned message: is_scam=%s confidence=%.2f score=%d entities=%d (%dms)",
            classification.is_scam,
            classification.confidence,
            risk.score,
            len(entities),
            processing_time_ms,
        )

        return ScanMessageResponse(
            result=ScanResult(
                is_scam=classification.is_scam,
                confidence=classification.confidence,
                scam_type=classification.scam_type.value,
                risk_level=risk.level.value,
                risk_score=risk.score,
                flagged_entities=entities,
                warning_message_en=warning_en,
                warning_message_hi=warning_hi,
                recommendation=recommendation,
                processing_time_ms=processing_time_ms,
            ),
            user_message_en=warning_en or "This message appears safe.",
            user_message_hi=warning_hi or "Yeh sandesh surakshit lagta hai.",
        )

    except Exception as e:
        logger.error("Error scanning message: %s", e, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Failed to scan message. Please try again.",
        )
