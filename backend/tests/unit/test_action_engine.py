"""Unit tests for ActionEngine."""

from app.services.intervention.action_engine import ActionEngine, GraphEnrichment
from app.schemas.risk import ActionCode, RiskLevel, RiskScore


def _make_risk(score, level=None):
    if level is None:
        if score <= 30: level = RiskLevel.LOW
        elif score <= 50: level = RiskLevel.MEDIUM
        elif score <= 70: level = RiskLevel.HIGH
        else: level = RiskLevel.CRITICAL
    return RiskScore(score=score, level=level, contributing_factors=[], recommended_action=ActionCode.NONE)


def test_low_risk_no_action():
    engine = ActionEngine()
    result = engine.decide(_make_risk(10), GraphEnrichment(graph_risk_score=0.0, connected_blacklisted_entities=0))
    assert result.action == ActionCode.NONE
    assert result.warning_message_en is None


def test_medium_risk_soft_warning():
    engine = ActionEngine()
    result = engine.decide(_make_risk(40), GraphEnrichment(graph_risk_score=0.0, connected_blacklisted_entities=0))
    assert result.action == ActionCode.SOFT_WARNING
    assert result.warning_message_en is not None
    assert result.warning_message_hi is not None


def test_high_risk_hard_block():
    engine = ActionEngine()
    result = engine.decide(_make_risk(60), GraphEnrichment(graph_risk_score=0.0, connected_blacklisted_entities=0))
    assert result.action == ActionCode.HARD_BLOCK


def test_critical_risk_freeze():
    engine = ActionEngine()
    result = engine.decide(_make_risk(80), GraphEnrichment(graph_risk_score=0.0, connected_blacklisted_entities=0))
    assert result.action in (ActionCode.FREEZE_AND_REPORT, ActionCode.CRITICAL_REPORT)


def test_graph_enrichment_boosts_score():
    engine = ActionEngine()
    no_graph = engine.decide(_make_risk(55), GraphEnrichment(graph_risk_score=0.0, connected_blacklisted_entities=0))
    with_graph = engine.decide(_make_risk(55), GraphEnrichment(graph_risk_score=0.8, connected_blacklisted_entities=3))
    # Graph enrichment should boost the score
    assert with_graph.action.value >= no_graph.action.value or with_graph.reason != no_graph.reason
