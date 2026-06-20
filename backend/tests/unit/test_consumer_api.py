"""Tests for consumer scan endpoint (no auth)."""

from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from app.main import app
from app.schemas.analyze import ClassificationResult, ScamType


client = TestClient(app, raise_server_exceptions=False)


@patch("app.services.nlp.warning_generator.WarningGenerator")
@patch("app.api.v1.consumer._get_services")
def test_consumer_scan_happy_path(mock_services, MockWarn):
    mock_pre = MagicMock()
    mock_pre.clean.return_value = "hello"
    mock_ext = MagicMock()
    mock_ext.extract.return_value = []
    mock_cls = AsyncMock()
    mock_cls.classify.return_value = ClassificationResult(
        is_scam=False, confidence=0.1, scam_type=ScamType.UNKNOWN, inference_time_ms=5
    )
    mock_scr = MagicMock()
    mock_scr.score.return_value = MagicMock(score=5, level=MagicMock(value="low"))

    mock_services.return_value = {
        "preprocessor": mock_pre,
        "extractor": mock_ext,
        "classifier": mock_cls,
        "scorer": mock_scr,
    }

    MockWarn.return_value.generate.return_value = {
        "warning_en": "Safe",
        "warning_hi": "Surakshit",
    }

    resp = client.post("/api/v1/consumer/scan", json={"text": "hello", "language": "en"})
    assert resp.status_code == 200
    data = resp.json()
    assert "risk_score" in data
    assert "recommendation" in data
    assert "recovery_steps" in data


def test_consumer_scan_validation_error():
    resp = client.post("/api/v1/consumer/scan", json={"text": ""})
    assert resp.status_code == 422
