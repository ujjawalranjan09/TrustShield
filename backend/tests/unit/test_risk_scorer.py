"""Unit tests for RiskScorer."""

from app.schemas.analyze import ClassificationResult, ScamType
from app.schemas.entity import EntityType, ExtractedEntity
from app.schemas.risk import RiskLevel
from app.services.nlp.risk_scorer import RiskScorer, SessionContext


def _make_context(confidence=0.5, entities=None, contact_by="user", reports=0):
    return SessionContext(
        classifier_output=ClassificationResult(
            is_scam=confidence > 0.5, confidence=confidence,
            scam_type=ScamType.VISHING, inference_time_ms=1,
        ),
        extracted_entities=entities or [],
        contact_initiated_by=contact_by,
        time_since_session_start=60,
        number_of_messages=3,
        is_during_active_upi_session=False,
        prior_reports_for_sender=reports,
    )


def test_low_risk():
    scorer = RiskScorer()
    ctx = _make_context(confidence=0.1)
    result = scorer.score(ctx)
    assert result.score <= 30
    assert result.level == RiskLevel.LOW


def test_high_risk_with_entities():
    scorer = RiskScorer()
    entity = ExtractedEntity(
        entity_type=EntityType.ANYDESK, value="123456789",
        start_char=0, end_char=9, confidence_score=0.99,
    )
    ctx = _make_context(confidence=0.9, entities=[entity], contact_by="unknown", reports=3)
    result = scorer.score(ctx)
    assert result.score >= 50
    assert result.level in (RiskLevel.HIGH, RiskLevel.CRITICAL)


def test_critical_risk():
    scorer = RiskScorer()
    entity = ExtractedEntity(
        entity_type=EntityType.TEAMVIEWER, value="987654321",
        start_char=0, end_char=9, confidence_score=0.99,
    )
    ctx = _make_context(confidence=0.95, entities=[entity], contact_by="unknown", reports=5)
    result = scorer.score(ctx)
    assert result.score >= 70
    assert result.level == RiskLevel.CRITICAL
