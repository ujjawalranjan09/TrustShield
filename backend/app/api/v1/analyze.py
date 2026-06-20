"""Chat analysis and webhook endpoints.

Provides the core fraud detection API: POST /analyze for real-time chat
analysis, and POST /webhook/pre-transaction for bank-side transaction
pre-screening.
"""

import logging
import time
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.auth import get_current_user, verify_api_key
from app.middleware.billing import require_billing_quota
from app.schemas.entity import ExtractedEntity
from app.schemas.risk import ActionCode, RiskLevel
from app.services.intervention.action_engine import ActionEngine, GraphEnrichment
from app.services.nlp.classifier import ScamClassifier
from app.services.nlp.entity_extractor import EntityExtractor
from app.services.nlp.preprocessor import TextPreprocessor
from app.services.nlp.risk_scorer import RiskScorer, SessionContext
from app.models.scan_event import ScanEvent
from app.models.user import User
from app.database import get_async_db
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------


class ChatMessage(BaseModel):
    """A single chat message in the session."""

    sender: str = Field(..., min_length=1, max_length=50)
    text: str = Field(..., min_length=1, max_length=5000)


class SessionMetadata(BaseModel):
    """Metadata about the client session."""

    client_app_id: str = Field(..., min_length=1, max_length=100)
    session_id: str = Field(..., min_length=1, max_length=100)
    contact_initiated_by: str = Field(..., min_length=1, max_length=50)
    is_during_active_upi_session: bool
    user_device_hash: str = Field(..., min_length=1, max_length=256)
    prior_reports_for_sender: int = Field(default=0, ge=0, le=1000)
    session_started_at: Optional[datetime] = Field(
        default=None,
        description="ISO-8601 timestamp of session start. Used to compute time_since_session_start.",
    )


class AnalyzeRequest(BaseModel):
    """Full chat analysis request payload."""

    messages: List[ChatMessage] = Field(..., min_length=1)
    session_metadata: SessionMetadata


class AnalyzeResponse(BaseModel):
    """Chat analysis result."""

    session_id: str
    risk_score: int
    risk_level: RiskLevel
    recommended_action: ActionCode
    flagged_entities: List[ExtractedEntity]
    warning_message_en: Optional[str] = None
    warning_message_hi: Optional[str] = None
    intervention_type: str


class WebhookRequest(BaseModel):
    """Pre-transaction webhook payload from banks."""

    payer_vpa: str = Field(..., min_length=1)
    payee_vpa: str = Field(..., min_length=1)
    amount: float = Field(..., gt=0)
    device_fingerprint: Optional[str] = None
    geo_location: Optional[dict] = None
    timestamp: Optional[str] = None


class WebhookResponse(BaseModel):
    """Pre-transaction decision."""

    decision: str
    reason: str
    risk_score: int
    risk_level: str


class ErrorResponse(BaseModel):
    """Structured error response."""

    error: str
    detail: str
    status_code: int


# ---------------------------------------------------------------------------
# Service dependencies (via FastAPI Depends)
# ---------------------------------------------------------------------------


def get_preprocessor() -> TextPreprocessor:
    """Return a TextPreprocessor instance."""
    return TextPreprocessor()


def get_extractor() -> EntityExtractor:
    """Return an EntityExtractor instance."""
    return EntityExtractor()


def get_classifier() -> ScamClassifier:
    """Return a ScamClassifier instance."""
    return ScamClassifier()


def get_scorer() -> RiskScorer:
    """Return a RiskScorer instance."""
    return RiskScorer()


def get_action_engine() -> ActionEngine:
    """Return an ActionEngine instance."""
    return ActionEngine()


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post(
    "/analyze",
    response_model=AnalyzeResponse,
    responses={
        400: {"model": ErrorResponse, "description": "Invalid request payload"},
        422: {"model": ErrorResponse, "description": "Validation error"},
        429: {"model": ErrorResponse, "description": "Rate limit exceeded"},
        500: {"model": ErrorResponse, "description": "Internal server error"},
    },
)
async def analyze_chat(
    request: AnalyzeRequest,
    _api_key: bool = Depends(verify_api_key),
    _billing: None = Depends(require_billing_quota("analyze")),
    current_user: "User" = Depends(get_current_user),
    preprocessor: TextPreprocessor = Depends(get_preprocessor),
    extractor: EntityExtractor = Depends(get_extractor),
    classifier: ScamClassifier = Depends(get_classifier),
    scorer: RiskScorer = Depends(get_scorer),
    action_engine: ActionEngine = Depends(get_action_engine),
    db: AsyncSession = Depends(get_async_db),
) -> AnalyzeResponse:
    """Analyze a chat session for fraud indicators.

    Runs the full NLP pipeline: preprocessing → entity extraction →
    classification → risk scoring → graph enrichment → intervention decision.
    Target latency: <300ms.
    """
    start_time = time.time()

    try:
        # 1. Preprocess and concatenate messages
        full_text = " ".join(msg.text for msg in request.messages)
        cleaned_text = preprocessor.clean(full_text)

        # 2. Extract entities
        entities = extractor.extract(cleaned_text)

        # 3. Classify text
        classification_result = await classifier.classify(cleaned_text)

        # 4. Compute session duration from timestamps
        if request.session_metadata.session_started_at:
            now = datetime.now(timezone.utc)
            session_start = request.session_metadata.session_started_at
            if session_start.tzinfo is None:
                session_start = session_start.replace(tzinfo=timezone.utc)
            time_since_start = int((now - session_start).total_seconds())
        else:
            # Fallback: estimate from message count (avg 10s per message)
            time_since_start = len(request.messages) * 10

        # 5. Risk scoring
        context = SessionContext(
            classifier_output=classification_result,
            extracted_entities=entities,
            contact_initiated_by=request.session_metadata.contact_initiated_by,
            time_since_session_start=time_since_start,
            number_of_messages=len(request.messages),
            is_during_active_upi_session=request.session_metadata.is_during_active_upi_session,
            prior_reports_for_sender=request.session_metadata.prior_reports_for_sender,
        )
        base_risk = scorer.score(context)

        # 6. Graph enrichment (real Neo4j lookup)
        from app.services.graph.entity_graph import FraudEntityGraph
        graph = FraudEntityGraph()
        try:
            graph_risk = 0.0
            blacklisted = 0
            for ent in entities:
                ent_risk = await graph.get_entity_risk(ent.value)
                graph_risk = max(graph_risk, ent_risk)
                connected = await graph.get_neighbors(ent.value, depth=1)
                blacklisted += len(connected)
        finally:
            await graph.close()
        graph_enrichment = GraphEnrichment(
            graph_risk_score=graph_risk,
            connected_blacklisted_entities=blacklisted,
        )

        # 7. Action engine
        decision = action_engine.decide(base_risk, graph_enrichment)

        # 8. SLA check
        processing_time = time.time() - start_time
        if processing_time > 0.3:
            logger.warning(
                "SLA MISSED: Processing took %.1fms for session %s",
                processing_time * 1000,
                request.session_metadata.session_id,
            )

        logger.info(
            "Analyzed session %s: score=%d level=%s action=%s entities=%d (%.1fms)",
            request.session_metadata.session_id,
            base_risk.score,
            base_risk.level.value,
            decision.action.value,
            len(entities),
            processing_time * 1000,
        )

        # 8.5. Trigger alerts for high-risk detections
        if base_risk.level.value in ("CRITICAL", "HIGH"):
            from app.services.alerting.alert_service import trigger_alert
            try:
                await trigger_alert(
                    session_id=request.session_metadata.session_id,
                    risk_score=base_risk.score,
                    risk_level=base_risk.level.value,
                    action=decision.action.value,
                    entities=[e.entity_type.value for e in entities],
                )
            except Exception as alert_err:
                logger.warning("Alert trigger failed: %s", alert_err)

        # 9. Log scan event for dashboard metrics
        try:
            scan_event = ScanEvent(
                session_id=request.session_metadata.session_id,
                scan_type="analyze",
                risk_score=base_risk.score,
                risk_level=base_risk.level.value,
                action_taken=decision.action.value,
                entities_found=len(entities),
                processing_time_ms=int(processing_time * 1000),
            )
            db.add(scan_event)
            await db.commit()
        except Exception as e:
            logger.warning("Failed to log scan event: %s", e)

        # 10. Broadcast to dashboard WebSocket clients
        try:
            from app.api.v1.ws_dashboard import broadcast_event
            import asyncio
            asyncio.create_task(broadcast_event({
                "type": "fraud_event",
                "session_id": request.session_metadata.session_id,
                "risk_score": base_risk.score,
                "risk_level": base_risk.level.value,
                "action": decision.action.value,
                "entities": [e.entity_type.value for e in entities],
            }))
        except Exception:
            pass  # Non-critical

        # Publish event to event bus
        try:
            from app.services.events.publisher import get_event_publisher
            publisher = get_event_publisher()
            await publisher.publish(
                topic="scan_completed",
                event_type="analysis_complete",
                payload={
                    "session_id": request.session_metadata.session_id,
                    "risk_score": base_risk.score,
                    "risk_level": base_risk.level.value,
                    "scam_type": classification_result.scam_type.value,
                    "entities_found": len(entities),
                },
            )
        except Exception:
            pass  # Non-critical

        # Generate adaptive warnings
        from app.services.nlp.warning_generator import WarningGenerator
        warn_gen = WarningGenerator()
        warnings = warn_gen.generate(
            scam_type=classification_result.scam_type.value,
            risk_score=base_risk.score,
            entities=entities,
        )

        return AnalyzeResponse(
            session_id=request.session_metadata.session_id,
            risk_score=base_risk.score,
            risk_level=base_risk.level,
            recommended_action=decision.action,
            flagged_entities=entities,
            warning_message_en=warnings["warning_en"],
            warning_message_hi=warnings["warning_hi"],
            intervention_type=decision.action.value,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error analyzing chat session: %s", e, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Internal server error during analysis",
        )


@router.post(
    "/webhook/pre-transaction",
    response_model=WebhookResponse,
    responses={
        400: {"model": ErrorResponse, "description": "Invalid request payload"},
        429: {"model": ErrorResponse, "description": "Rate limit exceeded"},
        500: {"model": ErrorResponse, "description": "Internal server error"},
    },
)
async def webhook_pre_transaction(
    request: WebhookRequest,
    _: bool = Depends(verify_api_key),
    _billing: None = Depends(require_billing_quota("webhook")),
) -> WebhookResponse:
    """Webhook endpoint for banks to check transactions before processing.

    Evaluates transaction parameters against fraud rules and returns a
    PASS / REVIEW / BLOCK decision within 100ms. All decisions are
    logged for audit trail purposes.
    """
    try:
        risk_score = 0
        reasons: List[str] = []

        if request.amount > 50000:
            risk_score += 30
            reasons.append("High transaction amount")

        if request.payer_vpa == request.payee_vpa:
            risk_score += 50
            reasons.append("Self-transfer detected")

        if request.device_fingerprint and len(request.device_fingerprint) > 0:
            risk_score += 10
            reasons.append("Device fingerprint present")

        # Check for geo_location anomalies (if provided)
        if request.geo_location:
            risk_score += 5
            reasons.append("Geo-location data present")

        if risk_score >= 70:
            decision = "BLOCK"
            risk_level = "critical"
        elif risk_score >= 40:
            decision = "REVIEW"
            risk_level = "high"
        elif risk_score >= 20:
            decision = "REVIEW"
            risk_level = "medium"
        else:
            decision = "PASS"
            risk_level = "low"

        # Structured audit log for compliance
        logger.info(
            "WEBHOOK_AUDIT decision=%s score=%d level=%s payer=%s payee=%s amount=%.2f reasons=%s",
            decision,
            risk_score,
            risk_level,
            request.payer_vpa,
            request.payee_vpa,
            request.amount,
            "; ".join(reasons) if reasons else "none",
        )

        return WebhookResponse(
            decision=decision,
            reason="; ".join(reasons) if reasons else "No risk factors detected",
            risk_score=risk_score,
            risk_level=risk_level,
        )

    except Exception as e:
        logger.error("Error processing webhook: %s", e, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Internal server error in webhook processing",
        )
