"""Unit tests for cell-aware routing middleware."""

import json
from unittest.mock import AsyncMock, patch

from starlette.applications import Starlette
from starlette.responses import PlainTextResponse
from starlette.testclient import TestClient

from app.middleware.cell_router import CellRoutingMiddleware, _reset_cell_url_cache


def _make_app():
    """Build a minimal Starlette app with CellRoutingMiddleware."""
    app = Starlette()

    async def homepage(request):
        return PlainTextResponse("ok")

    app.add_route("/", homepage)
    app.add_route("/health", homepage)

    app.add_middleware(CellRoutingMiddleware)
    return app


def test_same_region_passes_through():
    """Request from tenant in same region should pass through."""
    _reset_cell_url_cache()
    app = _make_app()

    with patch("app.middleware.cell_router.settings") as mock_settings:
        mock_settings.cell_region = "ap-south-1"
        mock_settings.cell_routing_enabled = True
        mock_settings.cell_urls = json.dumps({
            "ap-south-1": "https://ap-south-1.trustshield.io",
            "us-east-1": "https://us-east-1.trustshield.io",
        })
        with patch(
            "app.middleware.cell_router._resolve_tenant_region",
            new_callable=AsyncMock,
            return_value="ap-south-1",
        ):
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.get("/")
            assert resp.status_code == 200
            assert resp.text == "ok"


def test_different_region_returns_redirect():
    """Request from tenant in different region should get 307 redirect."""
    _reset_cell_url_cache()
    app = _make_app()

    with patch("app.middleware.cell_router.settings") as mock_settings:
        mock_settings.cell_region = "ap-south-1"
        mock_settings.cell_routing_enabled = True
        mock_settings.cell_urls = json.dumps({
            "ap-south-1": "https://ap-south-1.trustshield.io",
            "us-east-1": "https://us-east-1.trustshield.io",
        })
        with patch(
            "app.middleware.cell_router._resolve_tenant_region",
            new_callable=AsyncMock,
            return_value="us-east-1",
        ):
            client = TestClient(app, raise_server_exceptions=False, follow_redirects=False)
            resp = client.get("/")
            assert resp.status_code == 307
            assert "us-east-1.trustshield.io" in resp.headers["location"]


def test_routing_disabled_passes_all():
    """When routing is disabled, all requests pass through regardless of region."""
    _reset_cell_url_cache()
    app = _make_app()

    with patch("app.middleware.cell_router.settings") as mock_settings:
        mock_settings.cell_region = "ap-south-1"
        mock_settings.cell_routing_enabled = False
        mock_settings.cell_urls = json.dumps({
            "us-east-1": "https://us-east-1.trustshield.io",
        })
        with patch(
            "app.middleware.cell_router._resolve_tenant_region",
            new_callable=AsyncMock,
            return_value="us-east-1",
        ):
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.get("/")
            assert resp.status_code == 200
            assert resp.text == "ok"


def test_no_pii_in_redirect():
    """Redirect URL should contain only cell URL + path, no PII."""
    _reset_cell_url_cache()
    app = _make_app()

    with patch("app.middleware.cell_router.settings") as mock_settings:
        mock_settings.cell_region = "ap-south-1"
        mock_settings.cell_routing_enabled = True
        mock_settings.cell_urls = json.dumps({
            "ap-south-1": "https://ap-south-1.trustshield.io",
            "us-east-1": "https://us-east-1.trustshield.io",
        })
        with patch(
            "app.middleware.cell_router._resolve_tenant_region",
            new_callable=AsyncMock,
            return_value="us-east-1",
        ):
            client = TestClient(app, raise_server_exceptions=False, follow_redirects=False)
            resp = client.get("/api/v1/analyze?phone=9876543210")
            assert resp.status_code == 307
            location = resp.headers["location"]
            assert "9876543210" not in location
            assert "us-east-1.trustshield.io" in location
            assert "/api/v1/analyze" in location


def test_health_endpoint_bypasses_routing():
    """Health endpoint should bypass cell routing."""
    _reset_cell_url_cache()
    app = _make_app()

    with patch("app.middleware.cell_router.settings") as mock_settings:
        mock_settings.cell_region = "ap-south-1"
        mock_settings.cell_routing_enabled = True
        mock_settings.cell_urls = json.dumps({
            "us-east-1": "https://us-east-1.trustshield.io",
        })
        with patch(
            "app.middleware.cell_router._resolve_tenant_region",
            new_callable=AsyncMock,
            return_value="us-east-1",
        ):
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.get("/health")
            assert resp.status_code == 200
            assert resp.text == "ok"


def test_unknown_region_passes_through():
    """If tenant region has no configured cell URL, request passes through."""
    _reset_cell_url_cache()
    app = _make_app()

    with patch("app.middleware.cell_router.settings") as mock_settings:
        mock_settings.cell_region = "ap-south-1"
        mock_settings.cell_routing_enabled = True
        mock_settings.cell_urls = json.dumps({
            "ap-south-1": "https://ap-south-1.trustshield.io",
        })
        with patch(
            "app.middleware.cell_router._resolve_tenant_region",
            new_callable=AsyncMock,
            return_value="eu-west-1",
        ):
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.get("/")
            assert resp.status_code == 200
            assert resp.text == "ok"


def test_no_tenant_passes_through():
    """If no tenant can be resolved, request passes through."""
    _reset_cell_url_cache()
    app = _make_app()

    with patch("app.middleware.cell_router.settings") as mock_settings:
        mock_settings.cell_region = "ap-south-1"
        mock_settings.cell_routing_enabled = True
        mock_settings.cell_urls = json.dumps({
            "us-east-1": "https://us-east-1.trustshield.io",
        })
        with patch(
            "app.middleware.cell_router._resolve_tenant_region",
            new_callable=AsyncMock,
            return_value=None,
        ):
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.get("/")
            assert resp.status_code == 200
            assert resp.text == "ok"
