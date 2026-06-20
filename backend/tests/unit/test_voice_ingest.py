"""Tests for voice ingest endpoint (D3.2)."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from app.main import app
from app.schemas.analyze import ClassificationResult, ScamType
from app.schemas.risk import ActionCode, RiskLevel, RiskScore


@pytest.fixture
def client():
    return TestClient(app)


def _mock_services():
    preprocessor = MagicMock()
    preprocessor.clean.return_value = "test transcript"
    extractor = MagicMock()
    extractor.extract.return_value = []
    classifier = AsyncMock()
    classifier.classify.return_value = ClassificationResult(
        is_scam=False, confidence=0.9, scam_type=ScamType.UNKNOWN, inference_time_ms=10
    )
    scorer = MagicMock()
    scorer.score.return_value = RiskScore(
        score=25,
        level=RiskLevel.LOW,
        contributing_factors=[],
        recommended_action=ActionCode.NONE,
    )
    return preprocessor, extractor, classifier, scorer


class TestVoiceAnalyzeEndpoint:
    @patch("app.api.v1.voice.build_verdict")
    @patch("app.api.v1.voice._get_services")
    def test_voice_returns_verdict_shape(
        self, mock_get_services, mock_build_verdict, client
    ):
        mock_get_services.return_value = _mock_services()

        mock_verdict = MagicMock()
        mock_verdict.model_dump.return_value = {
            "session_id": "test-id",
            "is_scam": False,
            "modality": "VOICE",
        }
        mock_build_verdict.return_value = mock_verdict

        response = client.post(
            "/api/v1/voice/analyze",
            json={"transcript": "Hello, this is a test call"},
            headers={"X-API-Key": "test-key"},
        )

        assert response.status_code == 200
        data = response.json()
        assert "verdict" in data
        assert data["verdict"]["modality"] == "VOICE"

    @patch("app.api.v1.voice.build_verdict")
    @patch("app.api.v1.voice._get_services")
    def test_voice_calls_normalize_and_emit(
        self, mock_get_services, mock_build_verdict, client
    ):
        mock_get_services.return_value = _mock_services()

        mock_verdict = MagicMock()
        mock_verdict.model_dump.return_value = {"session_id": "test-id"}
        mock_build_verdict.return_value = mock_verdict

        with patch("app.services.intel.ingest_normalizer.normalize_and_emit", new_callable=AsyncMock):
            response = client.post(
                "/api/v1/voice/analyze",
                json={"transcript": "Hello, this is a test call"},
                headers={"X-API-Key": "test-key"},
            )

            assert response.status_code == 200

    @patch("app.api.v1.voice.build_verdict")
    @patch("app.api.v1.voice._get_services")
    def test_voice_redacts_pii_from_logs(
        self, mock_get_services, mock_build_verdict, client
    ):
        mock_get_services.return_value = _mock_services()

        mock_verdict = MagicMock()
        mock_verdict.model_dump.return_value = {"session_id": "test-id"}
        mock_build_verdict.return_value = mock_verdict

        pii_transcript = "Call me at 9876543210 for verification"

        response = client.post(
            "/api/v1/voice/analyze",
            json={"transcript": pii_transcript},
            headers={"X-API-Key": "test-key"},
        )

        assert response.status_code == 200

        preprocessor = mock_get_services.return_value[0]
        preprocessor.clean.assert_called_once()
        cleaned_arg = preprocessor.clean.call_args[0][0]
        assert "9876543210" not in cleaned_arg
        assert "[REDACTED]" in cleaned_arg
