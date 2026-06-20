"""Unit tests for model loader and remote client."""

import asyncio

import pytest
from unittest.mock import MagicMock, patch


class TestModelLoaderFactory:
    def test_empty_url_uses_inprocess(self, monkeypatch):
        monkeypatch.setattr("app.services.nlp.model_loader.settings", type("S", (), {
            "model_service_url": "",
            "model_service_timeout_ms": 100,
        })())

        from app.services.nlp.model_loader import get_loader, ModelLoader

        loader = get_loader()
        assert isinstance(loader, ModelLoader)

    def test_remote_url_uses_remote_client(self, monkeypatch):
        monkeypatch.setattr("app.services.nlp.model_loader.settings", type("S", (), {
            "model_service_url": "http://localhost:3000",
            "model_service_timeout_ms": 100,
        })())

        from app.services.nlp.model_loader import get_loader, RemoteModelClient

        loader = get_loader()
        assert isinstance(loader, RemoteModelClient)


class TestRemoteModelClient:
    def test_timeout_raises_unavailable(self):
        from app.services.nlp.model_loader import RemoteModelClient, ModelServiceUnavailable

        client = RemoteModelClient(base_url="http://localhost:9999", timeout_ms=1)
        mock_http_client = MagicMock()
        import httpx
        mock_http_client.post.side_effect = httpx.TimeoutException("timeout")
        client._client = mock_http_client

        with pytest.raises(ModelServiceUnavailable):
            asyncio.run(client.classify_transformer("test"))

    def test_5xx_raises_unavailable(self):
        from app.services.nlp.model_loader import RemoteModelClient, ModelServiceUnavailable

        client = RemoteModelClient(base_url="http://localhost:9999", timeout_ms=100)
        mock_http_client = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 500
        import httpx
        mock_http_client.post.side_effect = httpx.HTTPStatusError(
            "error", request=MagicMock(), response=mock_response
        )
        client._client = mock_http_client

        with pytest.raises(ModelServiceUnavailable):
            asyncio.run(client.classify_transformer("test"))

    def test_load_is_noop(self):
        from app.services.nlp.model_loader import RemoteModelClient

        client = RemoteModelClient(base_url="http://localhost:3000")
        client.load()  # Should not raise

    def test_transformer_available_property(self):
        from app.services.nlp.model_loader import RemoteModelClient

        client = RemoteModelClient(base_url="http://localhost:3000")
        assert client.transformer_available is True
        assert client.gbm_available is True
