from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional
import time

from app.schemas.entity import ExtractedEntity
from app.schemas.risk import RiskLevel, ActionCode
from app.services.nlp.preprocessor import TextPreprocessor
from app.services.nlp.entity_extractor import EntityExtractor
from app.services.nlp.classifier import ScamClassifier
from app.services.nlp.risk_scorer import RiskScorer, SessionContext
from app.services.intervention.action_engine import ActionEngine, GraphEnrichment

router = APIRouter()

class ChatMessage(BaseModel):
    sender: str
    text: str

class SessionMetadata(BaseModel):
    client_app_id: str
    session_id: str
    contact_initiated_by: str
    is_during_active_upi_session: bool
    user_device_hash: str
    prior_reports_for_sender: int = 0

class AnalyzeRequest(BaseModel):
    messages: List[ChatMessage]
    session_metadata: SessionMetadata

class AnalyzeResponse(BaseModel):
    session_id: str
    risk_score: int
    risk_level: RiskLevel
    recommended_action: ActionCode
    flagged_entities: List[ExtractedEntity]
    warning_message_en: Optional[str]
    warning_message_hi: Optional[str]
    intervention_type: str

# Instantiate services
preprocessor = TextPreprocessor()
extractor = EntityExtractor()
classifier = ScamClassifier()
scorer = RiskScorer()
action_engine = ActionEngine()

@router.post("/analyze", response_model=AnalyzeResponse)
async def analyze_chat(request: AnalyzeRequest):
    start_time = time.time()

    # 1. Preprocess and concatenate messages
    full_text = " ".join([msg.text for msg in request.messages])
    cleaned_text = preprocessor.clean(full_text)

    # 2. Extract Entities
    entities = extractor.extract(cleaned_text)

    # 3. Classify text
    classification_result = await classifier.classify(cleaned_text)

    # 4. Risk Scoring
    context = SessionContext(
        classifier_output=classification_result,
        extracted_entities=entities,
        contact_initiated_by=request.session_metadata.contact_initiated_by,
        time_since_session_start=len(request.messages) * 10, # Mock time
        number_of_messages=len(request.messages),
        is_during_active_upi_session=request.session_metadata.is_during_active_upi_session,
        prior_reports_for_sender=request.session_metadata.prior_reports_for_sender
    )
    base_risk = scorer.score(context)

    # 5. Graph Enrichment (Mocked)
    graph_enrichment = GraphEnrichment(
        graph_risk_score=0.2 if any(e.entity_type.value == "PHONE" for e in entities) else 0.0,
        connected_blacklisted_entities=0
    )

    # 6. Action Engine
    decision = action_engine.decide(base_risk, graph_enrichment)

    # 7. Simulated DB writes & Kafka emit
    # (Mocked: store session, write entities to Neo4j, emit Kafka event)

    processing_time = time.time() - start_time
    if processing_time > 0.3:
        # We missed 300ms SLA, log it
        print(f"SLA MISSED: Processing took {processing_time * 1000}ms")

    return AnalyzeResponse(
        session_id=request.session_metadata.session_id,
        risk_score=base_risk.score,
        risk_level=base_risk.level,
        recommended_action=decision.action,
        flagged_entities=entities,
        warning_message_en=decision.warning_message_en,
        warning_message_hi=decision.warning_message_hi,
        intervention_type=decision.action.value
    )
