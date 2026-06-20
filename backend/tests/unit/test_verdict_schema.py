from datetime import datetime, timezone

from app.schemas.analyze import ScamType
from app.schemas.entity import EntityType, ExtractedEntity
from app.schemas.risk import ActionCode, RiskLevel, ShapAttribution
from app.services.intel.verdict import Modality, Verdict, build_verdict


def _make_entities():
    return [
        ExtractedEntity(
            entity_type=EntityType.UPI,
            value="user@bank",
            start_char=0,
            end_char=9,
            confidence_score=0.95,
        )
    ]


def _make_attributions():
    return [
        ShapAttribution(
            feature="urgency_words",
            value=1.0,
            shap_value=0.4,
            direction="increases",
        )
    ]


def test_verdict_required_fields():
    now = datetime.now(timezone.utc)
    v = Verdict(
        session_id="s1",
        is_scam=True,
        scam_type=ScamType.VISHING,
        risk_score=72.5,
        risk_level=RiskLevel.HIGH,
        confidence=0.88,
        recommended_action=ActionCode.HARD_BLOCK,
        entities=_make_entities(),
        modality=Modality.TEXT,
        attributions=_make_attributions(),
        model_tier="standard",
        created_at=now,
    )
    assert v.session_id == "s1"
    assert v.is_scam is True
    assert v.scam_type == ScamType.VISHING
    assert v.risk_score == 72.5
    assert v.risk_level == RiskLevel.HIGH
    assert v.confidence == 0.88
    assert v.recommended_action == ActionCode.HARD_BLOCK
    assert len(v.entities) == 1
    assert v.modality == Modality.TEXT
    assert len(v.attributions) == 1
    assert v.model_tier == "standard"
    assert v.created_at == now


def test_build_verdict_from_text():
    v = build_verdict(
        session_id="t1",
        is_scam=False,
        scam_type=ScamType.PHISHING,
        risk_score=15.0,
        risk_level=RiskLevel.LOW,
        confidence=0.92,
        recommended_action=ActionCode.NONE,
        entities=[],
        modality=Modality.TEXT,
    )
    assert v.modality == Modality.TEXT
    assert v.is_scam is False
    assert v.attributions == []
    assert v.model_tier == "unknown"
    assert isinstance(v.created_at, datetime)


def test_build_verdict_from_voice():
    v = build_verdict(
        session_id="v1",
        is_scam=True,
        scam_type=ScamType.FAKE_SUPPORT,
        risk_score=88.0,
        risk_level=RiskLevel.CRITICAL,
        confidence=0.95,
        recommended_action=ActionCode.FREEZE_AND_REPORT,
        entities=_make_entities(),
        modality=Modality.VOICE,
        attributions=_make_attributions(),
        model_tier="ultra",
    )
    assert v.modality == Modality.VOICE
    assert v.scam_type == ScamType.FAKE_SUPPORT
    assert v.model_tier == "ultra"


def test_build_verdict_from_image():
    v = build_verdict(
        session_id="i1",
        is_scam=True,
        scam_type=ScamType.OTP_HARVESTING,
        risk_score=65.0,
        risk_level=RiskLevel.HIGH,
        confidence=0.80,
        recommended_action=ActionCode.SOFT_WARNING,
        entities=[],
        modality=Modality.IMAGE,
    )
    assert v.modality == Modality.IMAGE
    assert v.recommended_action == ActionCode.SOFT_WARNING


def test_back_compat():
    now = datetime.now(timezone.utc)
    data = {
        "session_id": "x1",
        "is_scam": True,
        "scam_type": "vishing",
        "risk_score": 50.0,
        "risk_level": "MEDIUM",
        "confidence": 0.75,
        "recommended_action": "NONE",
        "entities": [],
        "modality": "TEXT",
        "attributions": [],
        "model_tier": "standard",
        "created_at": now.isoformat(),
        "extra_unknown_field": "should_be_ignored",
        "legacy_score": 999,
    }
    v = Verdict.model_validate(data)
    assert v.session_id == "x1"
    assert v.scam_type == ScamType.VISHING
    assert v.risk_level == RiskLevel.MEDIUM
