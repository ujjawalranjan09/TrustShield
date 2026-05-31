"""Voice Call Analysis endpoint.

Provides real-time voice transcription analysis for anti-vishing.
Receives audio chunks or pre-transcribed text, runs it through the
NLP pipeline, and returns scam detection results.

Designed for integration with WebSocket streaming (live call monitoring)
or batch analysis of recorded calls.

In production, integrates with Whisper/Deepgram for audio-to-text.
"""

import logging
import time
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

from app.auth import verify_api_key
from app.schemas.risk import ActionCode, RiskLevel
from app.services.nlp.classifier import ScamClassifier
from app.services.nlp.entity_extractor import EntityExtractor
from app.services.nlp.preprocessor import TextPreprocessor
from app.services.nlp.risk_scorer import RiskScorer, SessionContext

logger = logging.getLogger(__name__)

router = APIRouter()

_preprocessor = TextPreprocessor()
_extractor = EntityExtractor()
_classifier = ScamClassifier()
_scorer = RiskScorer()


# ---------------------------------------------------------------------------
# REST Schemas
# ---------------------------------------------------------------------------


class ErrorResponse(BaseModel):
    """Structured error response."""

    error: str
    detail: str
    status_code: int


class VoiceAnalysisRequest(BaseModel):
    """Analyze a transcribed voice call segment."""

    transcript: str = Field(..., min_length=1, max_length=10000)
    caller_id: Optional[str] = Field(None, max_length=100)
    call_duration_seconds: Optional[int] = Field(None, ge=0)
    is_incoming: bool = Field(
        default=True, description="True if the user received the call"
    )


class VoiceAnalysisResponse(BaseModel):
    """Result of voice call analysis."""

    is_scam: bool
    confidence: float
    scam_type: str
    risk_score: int
    risk_level: str
    flagged_entities: list
    warning_en: Optional[str] = None
    warning_hi: Optional[str] = None
    processing_time_ms: int


class VoiceStreamMessage(BaseModel):
    """Message sent over the WebSocket stream."""

    type: str  # 'transcript_chunk', 'analysis_result', 'alert'
    data: dict


# ---------------------------------------------------------------------------
# REST Endpoint
# ---------------------------------------------------------------------------


@router.post(
    "/voice/analyze",
    response_model=VoiceAnalysisResponse,
    responses={500: {"model": ErrorResponse}},
)
async def analyze_voice_transcript(
    request: VoiceAnalysisRequest,
    _: bool = Depends(verify_api_key),
) -> VoiceAnalysisResponse:
    """Analyze a voice call transcript for scam indicators.

    Accepts pre-transcribed text from Whisper/Deepgram and runs it
    through the NLP pipeline. For real-time analysis, use the WebSocket
    endpoint instead.
    """
    start_time = time.time()

    try:
        cleaned = _preprocessor.clean(request.transcript)
        entities = _extractor.extract(cleaned)
        classification = await _classifier.classify(cleaned)

        context = SessionContext(
            classifier_output=classification,
            extracted_entities=entities,
            contact_initiated_by="unknown" if request.is_incoming else "known",
            time_since_session_start=(request.call_duration_seconds or 0),
            number_of_messages=1,
            is_during_active_upi_session=False,
            prior_reports_for_sender=0,
        )
        risk = _scorer.score(context)

        warning_en = None
        warning_hi = None
        if risk.score >= 70:
            warning_en = "Critical: This call shows strong signs of a vishing attack!"
            warning_hi = "Gambhir: Yeh call vishing hamla lag raha hai!"
        elif risk.score >= 40:
            warning_en = "Warning: Suspicious patterns detected in this call."
            warning_hi = "Chetawani: Is call mein sandehjanak patterns hain."

        processing_time_ms = max(1, int((time.time() - start_time) * 1000))

        return VoiceAnalysisResponse(
            is_scam=classification.is_scam,
            confidence=classification.confidence,
            scam_type=classification.scam_type.value,
            risk_score=risk.score,
            risk_level=risk.level.value,
            flagged_entities=[e.model_dump() for e in entities],
            warning_en=warning_en,
            warning_hi=warning_hi,
            processing_time_ms=processing_time_ms,
        )

    except Exception as e:
        logger.error("Error analyzing voice transcript: %s", e, exc_info=True)
        raise HTTPException(
            status_code=500, detail="Failed to analyze voice transcript"
        )


# ---------------------------------------------------------------------------
# WebSocket for real-time streaming
# ---------------------------------------------------------------------------


@router.websocket("/voice/stream")
async def voice_stream_websocket(websocket: WebSocket) -> None:
    """Real-time voice call analysis over WebSocket.

    Clients stream transcript chunks and receive instant analysis results.
    Protocol:
      1. Client sends: {"type": "transcript_chunk", "text": "...", "caller_id": "..."}
      2. Server responds: {"type": "analysis_result", "risk_score": 75, ...}
      3. Server pushes: {"type": "alert", "message": "..."} when risk >= 70

    In production, add authentication via the first message or query param.
    """
    await websocket.accept()
    logger.info("Voice stream WebSocket connected")

    accumulated_text = ""
    caller_id = ""

    try:
        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type", "")

            if msg_type == "transcript_chunk":
                chunk = data.get("text", "")
                caller_id = data.get("caller_id", caller_id)
                accumulated_text += " " + chunk

                # Analyze accumulated transcript
                cleaned = _preprocessor.clean(accumulated_text)
                entities = _extractor.extract(cleaned)
                classification = await _classifier.classify(cleaned)

                context = SessionContext(
                    classifier_output=classification,
                    extracted_entities=entities,
                    contact_initiated_by="unknown",
                    time_since_session_start=0,
                    number_of_messages=1,
                    is_during_active_upi_session=False,
                    prior_reports_for_sender=0,
                )
                risk = _scorer.score(context)

                result = {
                    "type": "analysis_result",
                    "risk_score": risk.score,
                    "risk_level": risk.level.value,
                    "is_scam": classification.is_scam,
                    "confidence": classification.confidence,
                    "scam_type": classification.scam_type.value,
                    "entities_found": len(entities),
                    "caller_id": caller_id,
                }
                await websocket.send_json(result)

                # Send alert if critical
                if risk.score >= 70:
                    alert = {
                        "type": "alert",
                        "message": "CRITICAL: Vishing attack detected in progress!",
                        "risk_score": risk.score,
                        "recommended_action": risk.recommended_action.value,
                    }
                    await websocket.send_json(alert)

            elif msg_type == "end":
                await websocket.send_json(
                    {"type": "stream_ended", "total_length": len(accumulated_text)}
                )
                break

    except WebSocketDisconnect:
        logger.info("Voice stream WebSocket disconnected")
    except Exception as e:
        logger.error("Voice stream error: %s", e)
        await websocket.close(code=1011, reason="Internal error")
