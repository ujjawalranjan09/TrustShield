"""Consumer-facing scan endpoint — public, no auth required."""

import logging
import time

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)
router = APIRouter()

_consumer_services = None


def _get_services():
    global _consumer_services
    if _consumer_services is None:
        from app.services.nlp.preprocessor import TextPreprocessor
        from app.services.nlp.entity_extractor import EntityExtractor
        from app.services.nlp.classifier import ScamClassifier
        from app.services.nlp.risk_scorer import RiskScorer
        _consumer_services = {
            "preprocessor": TextPreprocessor(),
            "extractor": EntityExtractor(),
            "classifier": ScamClassifier(),
            "scorer": RiskScorer(),
        }
    return _consumer_services


class ConsumerScanRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=5000)
    language: str = Field(default="en")


class ConsumerScanResponse(BaseModel):
    risk_score: int
    risk_level: str
    scam_type: str
    warning_en: str
    warning_hi: str
    recommendation: str
    recovery_steps: list


@router.post("/consumer/scan", response_model=ConsumerScanResponse)
async def consumer_scan(request: ConsumerScanRequest):
    """Public scan endpoint for consumer PWA. No auth required, rate-limited."""
    start_time = time.time()

    try:
        services = _get_services()
        cleaned = services["preprocessor"].clean(request.text)
        entities = services["extractor"].extract(cleaned)
        classification = await services["classifier"].classify(cleaned)

        from app.services.nlp.risk_scorer import SessionContext
        context = SessionContext(
            classifier_output=classification,
            extracted_entities=entities,
            contact_initiated_by="unknown",
            time_since_session_start=0,
            number_of_messages=1,
            is_during_active_upi_session=False,
            prior_reports_for_sender=0,
        )
        risk = services["scorer"].score(context)

        from app.services.nlp.warning_generator import WarningGenerator
        gen = WarningGenerator()
        warnings = gen.generate(
            scam_type=classification.scam_type.value,
            risk_score=risk.score,
            entities=entities,
            locale=request.language,
        )

        recovery_steps = _get_recovery_steps(classification.scam_type.value)

        return ConsumerScanResponse(
            risk_score=risk.score,
            risk_level=risk.level.value,
            scam_type=classification.scam_type.value,
            warning_en=warnings["warning_en"],
            warning_hi=warnings["warning_hi"],
            recommendation=recovery_steps["recommendation"],
            recovery_steps=recovery_steps["steps"],
        )

    except Exception as e:
        logger.error("Consumer scan error: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Scan failed. Please try again.")


def _get_recovery_steps(scam_type: str) -> dict:
    steps_map = {
        "otp_harvesting": {
            "recommendation": "Do NOT share your OTP. Block the sender. Call your bank immediately.",
            "steps": ["Never share OTP with anyone", "Block the sender", "Call bank helpline", "File complaint at cybercrime.gov.in"],
        },
        "vishing": {
            "recommendation": "Hang up immediately. Call your bank's official number to verify.",
            "steps": ["Hang up the call", "Call bank official number", "Do not share any details", "File complaint if money lost"],
        },
        "remote_access": {
            "recommendation": "Do NOT install AnyDesk/TeamViewer. Uninstall if already installed.",
            "steps": ["Do not install remote access apps", "If installed, uninstall immediately", "Disconnect from internet", "Block all cards", "File complaint"],
        },
        "refund_scam": {
            "recommendation": "Do NOT scan QR codes to receive money. You will lose money instead.",
            "steps": ["Do not scan the QR code", "Do not enter UPI PIN", "Block the sender", "Report to NPCI"],
        },
    }
    return steps_map.get(scam_type, {
        "recommendation": "Stay cautious. Verify the sender independently.",
        "steps": ["Do not share personal information", "Verify sender identity", "Report if suspicious"],
    })
