"""Tests for scan-message endpoint."""

from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from app.main import app
from app.auth import verify_api_key
from app.schemas.analyze import ClassificationResult, ScamType


client = TestClient(app, raise_server_exceptions=False)


@patch("app.services.nlp.warning_generator.WarningGenerator")
@patch("app.api.v1.scan._get_services")
def test_scan_message_happy_path(mock_services, MockWarn):
    app.dependency_overrides[verify_api_key] = lambda: True
    try:
        mock_pre = MagicMock()
        mock_pre.clean.return_value = "hello"
        mock_pre.detect_language.return_value = "en"
        mock_ext = MagicMock()
        mock_ext.extract.return_value = []
        mock_cls = AsyncMock()
        mock_cls.classify.return_value = ClassificationResult(
            is_scam=False, confidence=0.1, scam_type=ScamType.UNKNOWN, inference_time_ms=5
        )
        mock_scr = MagicMock()
        mock_scr.score.return_value = MagicMock(score=5, level=MagicMock(value="low"))

        mock_services.return_value = (mock_pre, mock_ext, mock_cls, mock_scr)
        MockWarn.return_value.generate.return_value = {
            "warning_en": "Safe",
            "warning_hi": "Surakshit",
        }

        resp = client.post("/api/v1/scan-message", json={"text": "hello"})
        assert resp.status_code == 200
        data = resp.json()
        assert "result" in data
        assert data["result"]["risk_score"] == 5
    finally:
        app.dependency_overrides.pop(verify_api_key, None)


def test_scan_message_validation_error():
    app.dependency_overrides[verify_api_key] = lambda: True
    try:
        resp = client.post("/api/v1/scan-message", json={"text": ""})
        assert resp.status_code == 422
    finally:
        app.dependency_overrides.pop(verify_api_key, None)
