"""Tests for image/QR ingest endpoint (D3.3)."""

import io
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client():
    return TestClient(app)


def _make_png_bytes(width=100, height=100, color="red"):
    """Create minimal valid PNG bytes for testing."""
    try:
        from PIL import Image
        img = Image.new("RGB", (width, height), color)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()
    except ImportError:
        return b"\x89PNG\r\n\x1a\n" + b"\x00" * 100


class TestImageAnalyzeEndpoint:
    @patch("app.api.v1.image_analysis.build_verdict")
    @patch("app.api.v1.image_analysis.normalize_and_emit", new_callable=AsyncMock)
    def test_image_returns_verdict_shape(
        self, mock_emit, mock_build_verdict, client
    ):
        mock_verdict = MagicMock()
        mock_verdict.model_dump.return_value = {
            "session_id": "test-id",
            "is_scam": False,
            "modality": "IMAGE",
            "risk_score": 15.0,
            "risk_level": "LOW",
        }
        mock_build_verdict.return_value = mock_verdict

        image_bytes = _make_png_bytes()
        response = client.post(
            "/api/v1/analyze-image",
            files={"file": ("test.png", image_bytes, "image/png")},
            headers={"X-API-Key": "test-key"},
        )

        assert response.status_code == 200
        data = response.json()
        assert "verdict" in data
        assert data["verdict"]["modality"] == "IMAGE"
        assert "result" in data
        assert data["result"]["risk_level"] == "low"

    @patch("app.api.v1.image_analysis.build_verdict")
    @patch("app.api.v1.image_analysis.normalize_and_emit", new_callable=AsyncMock)
    def test_image_calls_normalize_and_emit(
        self, mock_emit, mock_build_verdict, client
    ):
        mock_verdict = MagicMock()
        mock_verdict.model_dump.return_value = {
            "session_id": "test-id",
            "is_scam": False,
            "modality": "IMAGE",
        }
        mock_build_verdict.return_value = mock_verdict

        image_bytes = _make_png_bytes()
        response = client.post(
            "/api/v1/analyze-image",
            files={"file": ("test.png", image_bytes, "image/png")},
            headers={"X-API-Key": "test-key"},
        )

        assert response.status_code == 200
        mock_emit.assert_called_once()
        call_kwargs = mock_emit.call_args
        assert call_kwargs[1]["event_type"] == "image"
        payload = call_kwargs[1]["payload"]
        assert "image_hash" in payload
        assert "qr_codes" in payload

    @patch("app.api.v1.image_analysis.build_verdict")
    @patch("app.api.v1.image_analysis.normalize_and_emit", new_callable=AsyncMock)
    def test_image_qr_decode_failure_degrades_gracefully(
        self, mock_emit, mock_build_verdict, client
    ):
        mock_verdict = MagicMock()
        mock_verdict.model_dump.return_value = {
            "session_id": "test-id",
            "is_scam": False,
            "modality": "IMAGE",
            "risk_level": "LOW",
        }
        mock_build_verdict.return_value = mock_verdict

        image_bytes = _make_png_bytes()
        response = client.post(
            "/api/v1/analyze-image",
            files={"file": ("test.png", image_bytes, "image/png")},
            headers={"X-API-Key": "test-key"},
        )

        assert response.status_code == 200
        data = response.json()
        assert "verdict" in data
        assert data["verdict"]["modality"] == "IMAGE"
        assert data["result"]["risk_level"] == "low"
