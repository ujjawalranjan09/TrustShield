"""Integration tests verifying all 3 modalities produce a consistent Verdict shape."""

from app.schemas.analyze import ScamType
from app.schemas.entity import EntityType, ExtractedEntity
from app.schemas.risk import ActionCode, RiskLevel
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


REQUIRED_VERDICT_FIELDS = {
    "session_id",
    "is_scam",
    "scam_type",
    "risk_score",
    "risk_level",
    "confidence",
    "recommended_action",
    "entities",
    "modality",
    "attributions",
    "model_tier",
    "created_at",
}


def _assert_verdict_shape(v: Verdict, modality: Modality):
    assert isinstance(v, Verdict)
    assert v.modality == modality
    missing = REQUIRED_VERDICT_FIELDS - set(Verdict.model_fields.keys())
    assert not missing, f"Missing fields: {missing}"
    assert 0 <= v.risk_score <= 100
    assert isinstance(v.entities, list)
    assert isinstance(v.attributions, list)
    assert v.model_tier in ("standard", "ultra", "unknown")
    assert v.session_id
    assert v.created_at is not None


class TestTextVerdict:
    def test_text_analyze_produces_verdict(self):
        v = build_verdict(
            session_id="text-sess-1",
            is_scam=True,
            scam_type=ScamType.VISHING,
            risk_score=72.5,
            risk_level=RiskLevel.HIGH,
            confidence=0.88,
            recommended_action=ActionCode.HARD_BLOCK,
            entities=_make_entities(),
            modality=Modality.TEXT,
        )
        _assert_verdict_shape(v, Modality.TEXT)


class TestVoiceVerdict:
    def test_voice_analyze_produces_verdict(self):
        v = build_verdict(
            session_id="voice-sess-1",
            is_scam=True,
            scam_type=ScamType.FAKE_SUPPORT,
            risk_score=88.0,
            risk_level=RiskLevel.CRITICAL,
            confidence=0.95,
            recommended_action=ActionCode.FREEZE_AND_REPORT,
            entities=_make_entities(),
            modality=Modality.VOICE,
            model_tier="ultra",
        )
        _assert_verdict_shape(v, Modality.VOICE)
        assert v.model_tier == "ultra"


class TestImageVerdict:
    def test_image_analyze_produces_verdict(self):
        v = build_verdict(
            session_id="img-sess-1",
            is_scam=True,
            scam_type=ScamType.OTP_HARVESTING,
            risk_score=65.0,
            risk_level=RiskLevel.HIGH,
            confidence=0.80,
            recommended_action=ActionCode.SOFT_WARNING,
            entities=[],
            modality=Modality.IMAGE,
        )
        _assert_verdict_shape(v, Modality.IMAGE)
        assert v.entities == []


class TestVerdictConsistency:
    def test_all_modalities_share_same_schema(self):
        verdicts = [
            build_verdict(
                session_id=f"{m.value.lower()}-s",
                is_scam=False,
                scam_type=ScamType.PHISHING,
                risk_score=10.0,
                risk_level=RiskLevel.LOW,
                confidence=0.7,
                recommended_action=ActionCode.NONE,
                entities=[],
                modality=m,
            )
            for m in Modality
        ]
        field_sets = [set(Verdict.model_fields.keys()) for v in verdicts]
        assert len(set(frozenset(fs) for fs in field_sets)) == 1
