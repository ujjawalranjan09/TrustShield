"""Tests for fixed image analysis with pyzbar/Pillow support."""

import io
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client():
    return TestClient(app)


def _make_png_bytes(width=100, height=100, color="blue"):
    """Create minimal valid PNG bytes for testing."""
    try:
        from PIL import Image
        img = Image.new("RGB", (width, height), color)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()
    except ImportError:
        return b"\x89PNG\r\n\x1a\n" + b"\x00" * 100


class TestImageAnalysisFixed:

    @patch("app.api.v1.image_analysis.build_verdict")
    @patch("app.api.v1.image_analysis.normalize_and_emit", new_callable=AsyncMock)
    def test_image_endpoint_returns_200_with_valid_image(
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
        assert "result" in data
        assert "verdict" in data
        assert data["result"]["risk_level"] in ["low", "medium", "high", "critical"]
        assert data["verdict"]["modality"] == "IMAGE"

    @patch("app.api.v1.image_analysis.build_verdict")
    @patch("app.api.v1.image_analysis.normalize_and_emit", new_callable=AsyncMock)
    def test_qr_decode_extracts_upi_entity(
        self, mock_emit, mock_build_verdict, client
    ):
        """Mock pyzbar to return a UPI QR code and verify entity extraction."""
        mock_verdict = MagicMock()
        mock_verdict.model_dump.return_value = {
            "session_id": "test-id",
            "is_scam": True,
            "modality": "IMAGE",
            "risk_score": 70.0,
            "risk_level": "HIGH",
        }
        mock_build_verdict.return_value = mock_verdict

        # Mock pyzbar QR decode result
        mock_qr_result = MagicMock()
        mock_qr_result.data = b"upi://pay?pa=merchant@okaxis&pn=Merchant&am=5000"

        import app.api.v1.image_analysis as img_mod
        original_decode = getattr(img_mod, "qr_decode", None)
        original_image = getattr(img_mod, "Image", None)
        original_io = getattr(img_mod, "io", None)
        original_flag = img_mod._image_deps_available
        setattr(img_mod, "qr_decode", lambda img: [mock_qr_result])
        setattr(img_mod, "Image", MagicMock())
        setattr(img_mod, "io", io)
        img_mod._image_deps_available = True
        try:
            image_bytes = _make_png_bytes()
            response = client.post(
                "/api/v1/analyze-image",
                files={"file": ("upi_qr.png", image_bytes, "image/png")},
                headers={"X-API-Key": "test-key"},
            )

            assert response.status_code == 200
            data = response.json()
            assert data["result"]["has_qr_code"] is True
            assert len(data["result"]["qr_codes"]) == 1
            qr = data["result"]["qr_codes"][0]
            assert qr["content_type"] == "upi_payment"
            assert "merchant@okaxis" in qr["content"]
        finally:
            if original_decode is not None:
                setattr(img_mod, "qr_decode", original_decode)
            elif hasattr(img_mod, "qr_decode"):
                delattr(img_mod, "qr_decode")
            if original_image is not None:
                setattr(img_mod, "Image", original_image)
            elif hasattr(img_mod, "Image"):
                delattr(img_mod, "Image")
            if original_io is not None:
                setattr(img_mod, "io", original_io)
            elif hasattr(img_mod, "io"):
                delattr(img_mod, "io")
            img_mod._image_deps_available = original_flag

    @patch("app.api.v1.image_analysis.build_verdict")
    @patch("app.api.v1.image_analysis.normalize_and_emit", new_callable=AsyncMock)
    def test_graceful_fallback_when_pyzbar_unavailable(
        self, mock_emit, mock_build_verdict, client
    ):
        """When pyzbar is not installed, endpoint still returns 200."""
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
        with patch("app.api.v1.image_analysis._image_deps_available", False):
            response = client.post(
                "/api/v1/analyze-image",
                files={"file": ("test.png", image_bytes, "image/png")},
                headers={"X-API-Key": "test-key"},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["result"]["has_qr_code"] is False
        assert data["result"]["qr_codes"] == []
        assert any("unavailable" in note.lower() for note in data["result"]["analysis_notes"])
