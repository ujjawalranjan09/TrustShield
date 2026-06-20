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
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

from app.auth import verify_api_key
from app.services.intel.verdict import Modality, build_verdict
from app.services.nlp.risk_scorer import SessionContext
from app.utils.pii import redact

logger = logging.getLogger(__name__)

router = APIRouter()

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
    verdict: Optional[dict] = None


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
    preprocessor, extractor, classifier, scorer = _get_services()

    # PII redaction before any logging or external calls
    redacted_transcript = redact(request.transcript)

    try:
        cleaned = preprocessor.clean(redacted_transcript)
        entities = extractor.extract(cleaned)
        classification = await classifier.classify(cleaned)

        context = SessionContext(
            classifier_output=classification,
            extracted_entities=entities,
            contact_initiated_by="unknown" if request.is_incoming else "known",
            time_since_session_start=(request.call_duration_seconds or 0),
            number_of_messages=1,
            is_during_active_upi_session=False,
            prior_reports_for_sender=0,
        )
        risk = scorer.score(context)

        warning_en = None
        warning_hi = None
        if risk.score >= 70:
            warning_en = "Critical: This call shows strong signs of a vishing attack!"
            warning_hi = "Gambhir: Yeh call vishing hamla lag raha hai!"
        elif risk.score >= 40:
            warning_en = "Warning: Suspicious patterns detected in this call."
            warning_hi = "Chetawani: Is call mein sandehjanak patterns hain."

        processing_time_ms = max(1, int((time.time() - start_time) * 1000))

        import uuid
        session_id = str(uuid.uuid4())

        verdict = build_verdict(
            session_id=session_id,
            is_scam=classification.is_scam,
            scam_type=classification.scam_type,
            risk_score=float(risk.score),
            risk_level=risk.level,
            confidence=classification.confidence,
            recommended_action=risk.recommended_action,
            entities=entities,
            modality=Modality.VOICE,
        )

        # Fire-and-forget: normalize and emit to sinks
        try:
            from app.services.intel.ingest_normalizer import normalize_and_emit
            import asyncio
            asyncio.create_task(normalize_and_emit(
                event_type="voice",
                payload={
                    "session_id": session_id,
                    "caller_id": request.caller_id,
                    "scam_type": classification.scam_type.value,
                    "risk_score": risk.score,
                    "risk_level": risk.level.value,
                    "flagged_entities": [e.model_dump() for e in entities],
                    "is_scam": classification.is_scam,
                    "confidence": classification.confidence,
                },
                db=None,
            ))
        except Exception as emit_err:
            logger.warning("Failed to emit voice ingest event: %s", emit_err)

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
            verdict=verdict.model_dump(mode="json"),
        )

    except Exception as e:
        logger.error("Error analyzing voice transcript: %s", redact(str(e)), exc_info=True)
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
                preprocessor, extractor, classifier, scorer = _get_services()
                cleaned = preprocessor.clean(accumulated_text)
                entities = extractor.extract(cleaned)
                classification = await classifier.classify(cleaned)

                context = SessionContext(
                    classifier_output=classification,
                    extracted_entities=entities,
                    contact_initiated_by="unknown",
                    time_since_session_start=0,
                    number_of_messages=1,
                    is_during_active_upi_session=False,
                    prior_reports_for_sender=0,
                )
                risk = scorer.score(context)

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


# ---------------------------------------------------------------------------
# WebSocket for real-time AUDIO streaming (Whisper/Deepgram)
# ---------------------------------------------------------------------------


@router.websocket("/voice/stream/audio")
async def voice_audio_stream_websocket(websocket: WebSocket) -> None:
    """Real-time voice call analysis via raw audio streaming.

    Accepts binary audio chunks (PCM 16-bit 16kHz), transcribes via
    Whisper/Deepgram, and runs NLP pipeline on transcribed text.

    Protocol:
      1. Client sends binary audio chunks
      2. Server buffers and transcribes periodically
      3. Server responds with analysis results as JSON
    """
    from app.services.voice.whisper_service import get_whisper_service

    await websocket.accept()
    logger.info("Voice audio stream WebSocket connected")

    whisper = get_whisper_service()
    audio_buffer = bytearray()
    accumulated_text = ""
    chunk_count = 0

    try:
        while True:
            data = await websocket.receive()

            if data["type"] == "websocket.receive":
                if "bytes" in data:
                    audio_buffer.extend(data["bytes"])
                    chunk_count += 1

                    # Transcribe every ~50 chunks (~1 second at 16kHz)
                    if chunk_count % 50 == 0 and len(audio_buffer) > 0:
                        transcript = await whisper.transcribe(bytes(audio_buffer))
                        audio_buffer = bytearray()

                        if transcript:
                            accumulated_text += " " + transcript

                            # Run NLP pipeline
                            preprocessor, extractor, classifier, scorer = _get_services()
                            cleaned = preprocessor.clean(accumulated_text)
                            entities = extractor.extract(cleaned)
                            classification = await classifier.classify(cleaned)

                            context = SessionContext(
                                classifier_output=classification,
                                extracted_entities=entities,
                                contact_initiated_by="unknown",
                                time_since_session_start=0,
                                number_of_messages=1,
                                is_during_active_upi_session=False,
                                prior_reports_for_sender=0,
                            )
                            risk = scorer.score(context)

                            result = {
                                "type": "analysis_result",
                                "transcript": transcript,
                                "full_text": accumulated_text[-200:],
                                "risk_score": risk.score,
                                "risk_level": risk.level.value,
                                "is_scam": classification.is_scam,
                                "confidence": classification.confidence,
                                "scam_type": classification.scam_type.value,
                                "entities_found": len(entities),
                            }
                            await websocket.send_json(result)

                            if risk.score >= 70:
                                await websocket.send_json({
                                    "type": "alert",
                                    "message": "CRITICAL: Vishing attack detected in progress!",
                                    "risk_score": risk.score,
                                })

                elif "text" in data:
                    msg = __import__("json").loads(data["text"])
                    if msg.get("type") == "end":
                        # Transcribe remaining buffer
                        if len(audio_buffer) > 0:
                            transcript = await whisper.transcribe(bytes(audio_buffer))
                            if transcript:
                                accumulated_text += " " + transcript
                        await websocket.send_json({
                            "type": "stream_ended",
                            "total_length": len(accumulated_text),
                        })
                        break

    except WebSocketDisconnect:
        logger.info("Voice audio stream disconnected")
    except Exception as e:
        logger.error("Voice audio stream error: %s", e)
        await websocket.close(code=1011, reason="Internal error")
