"""Unit tests for NLP service modules."""

import pytest
from app.services.nlp.preprocessor import TextPreprocessor
from app.services.nlp.entity_extractor import EntityExtractor
from app.services.nlp.classifier import ScamClassifier
from app.services.nlp.risk_scorer import RiskScorer, SessionContext
from app.services.intervention.action_engine import ActionEngine, GraphEnrichment
from app.schemas.analyze import ClassificationResult, ScamType
from app.schemas.entity import EntityType, ExtractedEntity
from app.schemas.risk import ActionCode, RiskLevel, RiskScore


# ---------------------------------------------------------------------------
# TextPreprocessor
# ---------------------------------------------------------------------------


class TestTextPreprocessor:
    """Tests for TextPreprocessor."""

    def setup_method(self):
        self.preprocessor = TextPreprocessor()

    def test_clean_normal_text(self):
        result = self.preprocessor.clean("Hello, this is a test message.")
        assert result == "Hello, this is a test message."

    def test_clean_unicode_characters(self):
        result = self.preprocessor.clean("Hello\u200bworld\u200ctest")
        assert "\u200b" not in result
        assert "\u200c" not in result

    def test_clean_duplicate_whitespace(self):
        result = self.preprocessor.clean("Hello   world   test")
        assert "   " not in result

    def test_clean_long_text(self):
        text = " ".join(["word"] * 600)
        result = self.preprocessor.clean(text)
        assert len(result.split()) <= 512

    def test_detect_language_english(self):
        assert self.preprocessor.detect_language("Hello, this is a test.") == "en"

    def test_detect_language_hindi(self):
        assert self.preprocessor.detect_language("aap kaise hain") == "hi"

    def test_detect_language_mixed(self):
        assert self.preprocessor.detect_language("aap please help karo") == "mixed"

    def test_detect_language_hinglish(self):
        assert self.preprocessor.detect_language("xyz abc123") == "hinglish"


# ---------------------------------------------------------------------------
# EntityExtractor
# ---------------------------------------------------------------------------


class TestEntityExtractor:
    """Tests for EntityExtractor."""

    def setup_method(self):
        self.extractor = EntityExtractor()

    def test_extract_upi_id(self):
        entities = self.extractor.extract("Send money to user@okaxis")
        upi_entities = [e for e in entities if e.entity_type == EntityType.UPI]
        assert len(upi_entities) >= 1
        assert upi_entities[0].value == "user@okaxis"

    def test_extract_phone_number(self):
        entities = self.extractor.extract("Call me at 9876543210")
        phone_entities = [e for e in entities if e.entity_type == EntityType.PHONE]
        assert len(phone_entities) >= 1

    def test_extract_phone_with_country_code(self):
        entities = self.extractor.extract("Call +91 98765 43210")
        phone_entities = [e for e in entities if e.entity_type == EntityType.PHONE]
        assert len(phone_entities) >= 1

    def test_extract_anydesk(self):
        entities = self.extractor.extract("AnyDesk ID 123456789")
        anydesk = [e for e in entities if e.entity_type == EntityType.ANYDESK]
        assert len(anydesk) >= 1
        assert anydesk[0].value == "123456789"

    def test_extract_teamviewer(self):
        entities = self.extractor.extract("TeamViewer code 9876543210")
        tv = [e for e in entities if e.entity_type == EntityType.TEAMVIEWER]
        assert len(tv) >= 1

    def test_extract_url_shortlink(self):
        entities = self.extractor.extract("Visit https://bit.ly/abc123")
        urls = [e for e in entities if e.entity_type == EntityType.URL_SHORTLINK]
        assert len(urls) >= 1

    def test_extract_ifsc(self):
        entities = self.extractor.extract("IFSC: HDFC0001234")
        ifsc = [e for e in entities if e.entity_type == EntityType.IFSC]
        assert len(ifsc) >= 1

    def test_extract_apk(self):
        entities = self.extractor.extract("Download malware.apk")
        apk = [e for e in entities if e.entity_type == EntityType.APK]
        assert len(apk) >= 1

    def test_no_entities_in_clean_text(self):
        entities = self.extractor.extract("Hello, how are you?")
        assert len(entities) == 0

    def test_multiple_entities(self):
        text = "Call 9876543210 or send to user@okaxis"
        entities = self.extractor.extract(text)
        types = {e.entity_type for e in entities}
        assert EntityType.PHONE in types
        assert EntityType.UPI in types


# ---------------------------------------------------------------------------
# ScamClassifier
# ---------------------------------------------------------------------------


class TestScamClassifier:
    """Tests for ScamClassifier."""

    def setup_method(self):
        self.classifier = ScamClassifier()

    @pytest.mark.asyncio
    async def test_classify_scam_otp(self):
        result = await self.classifier.classify("Please share your OTP batao")
        assert result.is_scam is True
        assert result.confidence > 0.7
        assert result.scam_type in [ScamType.OTP_HARVESTING, ScamType.VISHING]

    @pytest.mark.asyncio
    async def test_classify_scam_anydesk(self):
        result = await self.classifier.classify("Download AnyDesk for remote access")
        assert result.is_scam is True
        assert result.confidence > 0.8
        assert result.scam_type == ScamType.REMOTE_ACCESS

    @pytest.mark.asyncio
    async def test_classify_scam_qr(self):
        result = await self.classifier.classify("Scan this QR code for refund")
        assert result.is_scam is True
        assert result.scam_type == ScamType.REFUND_SCAM

    @pytest.mark.asyncio
    async def test_classify_legitimate(self):
        result = await self.classifier.classify("When will my order be delivered?")
        assert result.is_scam is False
        assert result.confidence < 0.25
        assert result.scam_type == ScamType.UNKNOWN

    @pytest.mark.asyncio
    async def test_classify_empty_text(self):
        result = await self.classifier.classify("")
        assert result.is_scam is False
        assert result.inference_time_ms >= 1

    @pytest.mark.asyncio
    async def test_multiple_signals_boost_confidence(self):
        result = await self.classifier.classify(
            "Share your OTP, download AnyDesk, enter PIN"
        )
        assert result.is_scam is True
        assert result.confidence > 0.9

    @pytest.mark.asyncio
    async def test_returns_inference_time(self):
        result = await self.classifier.classify("hello")
        assert result.inference_time_ms >= 1


# ---------------------------------------------------------------------------
# RiskScorer
# ---------------------------------------------------------------------------


class TestRiskScorer:
    """Tests for RiskScorer."""

    def setup_method(self):
        self.scorer = RiskScorer()

    def _make_context(
        self,
        confidence: float = 0.5,
        scam_type: ScamType = ScamType.VISHING,
        entities=None,
        contact_by: str = "known",
        prior_reports: int = 0,
        active_upi: bool = False,
    ) -> SessionContext:
        return SessionContext(
            classifier_output=ClassificationResult(
                is_scam=confidence > 0.5,
                confidence=confidence,
                scam_type=scam_type,
                inference_time_ms=10,
            ),
            extracted_entities=entities or [],
            contact_initiated_by=contact_by,
            time_since_session_start=60,
            number_of_messages=3,
            is_during_active_upi_session=active_upi,
            prior_reports_for_sender=prior_reports,
        )

    def test_low_risk(self):
        ctx = self._make_context(confidence=0.1, contact_by="known")
        result = self.scorer.score(ctx)
        assert result.level == RiskLevel.LOW
        assert result.score <= 30

    def test_high_risk_unknown_contact(self):
        ctx = self._make_context(confidence=0.9, contact_by="unknown", prior_reports=3)
        result = self.scorer.score(ctx)
        assert result.level in [RiskLevel.HIGH, RiskLevel.CRITICAL]
        assert result.score > 50

    def test_critical_risk(self):
        entities = [
            ExtractedEntity(
                entity_type=EntityType.ANYDESK,
                value="123456789",
                start_char=0,
                end_char=9,
                confidence_score=0.99,
            )
        ]
        ctx = self._make_context(
            confidence=0.95,
            entities=entities,
            contact_by="unknown",
            prior_reports=5,
        )
        result = self.scorer.score(ctx)
        assert result.level == RiskLevel.CRITICAL
        assert result.score >= 85

    def test_contributing_factors(self):
        ctx = self._make_context(confidence=0.9, contact_by="unknown", prior_reports=2)
        result = self.scorer.score(ctx)
        assert len(result.contributing_factors) >= 2

    def test_score_capped_at_100(self):
        entities = [
            ExtractedEntity(
                entity_type=EntityType.ANYDESK,
                value="x",
                start_char=0,
                end_char=1,
                confidence_score=0.99,
            )
        ]
        ctx = self._make_context(
            confidence=1.0,
            entities=entities,
            contact_by="unknown",
            prior_reports=100,
        )
        result = self.scorer.score(ctx)
        assert result.score <= 100


# ---------------------------------------------------------------------------
# ActionEngine
# ---------------------------------------------------------------------------


class TestActionEngine:
    """Tests for ActionEngine."""

    def setup_method(self):
        self.engine = ActionEngine()

    def _make_risk(self, score: int) -> RiskScore:
        if score <= 30:
            level = RiskLevel.LOW
        elif score <= 50:
            level = RiskLevel.MEDIUM
        elif score <= 70:
            level = RiskLevel.HIGH
        else:
            level = RiskLevel.CRITICAL
        return RiskScore(
            score=score,
            level=level,
            contributing_factors=[],
            recommended_action=ActionCode.NONE,
        )

    def test_low_risk_no_action(self):
        decision = self.engine.decide(
            self._make_risk(20),
            GraphEnrichment(graph_risk_score=0.0, connected_blacklisted_entities=0),
        )
        assert decision.action == ActionCode.NONE
        assert decision.warning_message_en is None

    def test_medium_risk_warning(self):
        decision = self.engine.decide(
            self._make_risk(40),
            GraphEnrichment(graph_risk_score=0.0, connected_blacklisted_entities=0),
        )
        assert decision.action == ActionCode.SOFT_WARNING
        assert decision.warning_message_en is not None

    def test_high_risk_block(self):
        decision = self.engine.decide(
            self._make_risk(60),
            GraphEnrichment(graph_risk_score=0.0, connected_blacklisted_entities=0),
        )
        assert decision.action == ActionCode.HARD_BLOCK

    def test_very_high_risk_freeze(self):
        decision = self.engine.decide(
            self._make_risk(80),
            GraphEnrichment(graph_risk_score=0.0, connected_blacklisted_entities=0),
        )
        assert decision.action == ActionCode.FREEZE_AND_REPORT

    def test_critical_risk_report(self):
        decision = self.engine.decide(
            self._make_risk(95),
            GraphEnrichment(graph_risk_score=0.0, connected_blacklisted_entities=0),
        )
        assert decision.action == ActionCode.CRITICAL_REPORT
        assert "1930" in decision.reason

    def test_graph_enrichment_boosts_score(self):
        decision = self.engine.decide(
            self._make_risk(50),
            GraphEnrichment(graph_risk_score=0.5, connected_blacklisted_entities=0),
        )
        # 50 + int(0.5 * 20) = 60 -> HARD_BLOCK
        assert decision.action == ActionCode.HARD_BLOCK
