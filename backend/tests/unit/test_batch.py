"""Tests for batch analysis endpoint."""

from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from app.main import app
from app.auth import verify_api_key
from app.schemas.analyze import ClassificationResult, ScamType
from app.schemas.risk import ActionCode, RiskLevel


client = TestClient(app, raise_server_exceptions=False)


def _batch_payload():
    return {
        "sessions": [
            {
                "session_metadata": {
                    "client_app_id": "test",
                    "session_id": "s1",
                    "contact_initiated_by": "unknown",
                    "is_during_active_upi_session": False,
                    "user_device_hash": "abc123",
                    "prior_reports_for_sender": 0,
                },
                "messages": [{"sender": "unknown", "text": "Send me your OTP"}],
            }
        ]
    }


@patch("app.api.v1.batch.get_action_engine")
@patch("app.api.v1.batch.get_scorer")
@patch("app.api.v1.batch.get_classifier")
@patch("app.api.v1.batch.get_extractor")
@patch("app.api.v1.batch.get_preprocessor")
def test_batch_analyze_happy_path(mock_pre, mock_ext, mock_cls, mock_scr, mock_ae):
    app.dependency_overrides[verify_api_key] = lambda: True
    try:
        mock_pre.return_value.clean.return_value = "send me your otp"
        mock_ext.return_value.extract.return_value = []

        classification = ClassificationResult(
            is_scam=True, confidence=0.9, scam_type=ScamType.OTP_HARVESTING, inference_time_ms=10
        )
        mock_cls_obj = AsyncMock()
        mock_cls_obj.classify.return_value = classification
        mock_cls.return_value = mock_cls_obj

        from app.services.nlp.risk_scorer import RiskScore
        risk_result = RiskScore(
            score=80, level=RiskLevel.HIGH, contributing_factors=["test"],
            recommended_action=ActionCode.HARD_BLOCK, model_version="test",
        )
        mock_scr.return_value.score.return_value = risk_result

        decision = MagicMock()
        decision.action = ActionCode.HARD_BLOCK
        decision.warning_message_en = "Warning"
        decision.warning_message_hi = "Chetavni"
        mock_ae.return_value.decide.return_value = decision

        resp = client.post("/api/v1/analyze/batch", json=_batch_payload())
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["processed"] == 1
        assert data["failed"] == 0
        assert len(data["results"]) == 1
    finally:
        app.dependency_overrides.pop(verify_api_key, None)


def test_batch_analyze_validation_error():
    app.dependency_overrides[verify_api_key] = lambda: True
    try:
        resp = client.post("/api/v1/analyze/batch", json={"sessions": []})
        assert resp.status_code == 422
    finally:
        app.dependency_overrides.pop(verify_api_key, None)
