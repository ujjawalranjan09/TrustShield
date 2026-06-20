"""Batch analysis endpoint for bulk fraud screening."""

import logging
import time
from typing import List

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.auth import verify_api_key
from app.api.v1.analyze import (
    AnalyzeRequest,
    AnalyzeResponse,
    get_action_engine,
    get_classifier,
    get_extractor,
    get_preprocessor,
    get_scorer,
)
from app.services.intervention.action_engine import GraphEnrichment
from app.services.nlp.risk_scorer import SessionContext
from datetime import datetime, timezone

logger = logging.getLogger(__name__)
router = APIRouter()


class BatchAnalyzeRequest(BaseModel):
    sessions: List[AnalyzeRequest] = Field(..., min_length=1, max_length=100)


class BatchAnalyzeResponse(BaseModel):
    total: int
    processed: int
    failed: int
    results: List[AnalyzeResponse]
    processing_time_ms: int


@router.post("/analyze/batch", response_model=BatchAnalyzeResponse)
async def batch_analyze(
    request: BatchAnalyzeRequest,
    _: bool = Depends(verify_api_key),
):
    """Analyze multiple chat sessions in a single request.

    Processes up to 100 sessions. Each session goes through the full
    NLP pipeline independently. Failed sessions are counted but don't
    abort the batch.
    """
    start_time = time.time()
    preprocessor = get_preprocessor()
    extractor = get_extractor()
    classifier = get_classifier()
    scorer = get_scorer()
    action_engine = get_action_engine()

    results: List[AnalyzeResponse] = []
    failed = 0

    for session_req in request.sessions:
        try:
            full_text = " ".join(msg.text for msg in session_req.messages)
            cleaned_text = preprocessor.clean(full_text)
            entities = extractor.extract(cleaned_text)
            classification = await classifier.classify(cleaned_text)

            if session_req.session_metadata.session_started_at:
                now = datetime.now(timezone.utc)
                session_start = session_req.session_metadata.session_started_at
                if session_start.tzinfo is None:
                    session_start = session_start.replace(tzinfo=timezone.utc)
                time_since = int((now - session_start).total_seconds())
            else:
                time_since = len(session_req.messages) * 10

            context = SessionContext(
                classifier_output=classification,
                extracted_entities=entities,
                contact_initiated_by=session_req.session_metadata.contact_initiated_by,
                time_since_session_start=time_since,
                number_of_messages=len(session_req.messages),
                is_during_active_upi_session=session_req.session_metadata.is_during_active_upi_session,
                prior_reports_for_sender=session_req.session_metadata.prior_reports_for_sender,
            )
            base_risk = scorer.score(context)
            graph_enrichment = GraphEnrichment(graph_risk_score=0.0, connected_blacklisted_entities=0)
            decision = action_engine.decide(base_risk, graph_enrichment)

            results.append(AnalyzeResponse(
                session_id=session_req.session_metadata.session_id,
                risk_score=base_risk.score,
                risk_level=base_risk.level,
                recommended_action=decision.action,
                flagged_entities=entities,
                warning_message_en=decision.warning_message_en,
                warning_message_hi=decision.warning_message_hi,
                intervention_type=decision.action.value,
            ))
        except Exception as e:
            failed += 1
            logger.error("Batch item failed (session=%s): %s",
                        session_req.session_metadata.session_id, e)

    processing_time = int((time.time() - start_time) * 1000)

    return BatchAnalyzeResponse(
        total=len(request.sessions),
        processed=len(results),
        failed=failed,
        results=results,
        processing_time_ms=processing_time,
    )
