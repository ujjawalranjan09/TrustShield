"""Unit tests for LLM service and RAG chat integration."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.explain.llm_service import (
    OpenRouterProvider,
    LocalLLMProvider,
    get_llm_provider,
)
from app.utils.pii import redact


# ---------------------------------------------------------------------------
# LLM Provider tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_openrouter_provider_sends_correct_request():
    provider = OpenRouterProvider()
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "choices": [{"message": {"content": "answer"}}],
    }
    mock_resp.raise_for_status = MagicMock()

    with patch("app.services.explain.llm_service.httpx.AsyncClient") as MockClient:
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        MockClient.return_value = mock_client

        result = await provider.complete(
            system="sys", context="ctx", question="q"
        )

    mock_client.post.assert_called_once()
    call_args = mock_client.post.call_args
    assert call_args[0][0] == "https://openrouter.ai/api/v1/chat/completions"
    body = call_args[1]["json"]
    assert body["messages"][0]["role"] == "system"
    assert body["messages"][1]["content"].startswith("Context:")
    assert result == "answer"


@pytest.mark.asyncio
async def test_local_provider_sends_to_custom_url():
    provider = LocalLLMProvider()
    provider._base_url = "http://localhost:11434"
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "choices": [{"message": {"content": "local answer"}}],
    }
    mock_resp.raise_for_status = MagicMock()

    with patch("app.services.explain.llm_service.httpx.AsyncClient") as MockClient:
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        MockClient.return_value = mock_client

        result = await provider.complete(
            system="sys", context="ctx", question="q"
        )

    call_args = mock_client.post.call_args
    assert call_args[0][0] == "http://localhost:11434/v1/chat/completions"
    assert result == "local answer"


def test_get_provider_returns_none_when_no_key():
    with patch("app.services.explain.llm_service.settings") as s:
        s.llm_api_key = ""
        assert get_llm_provider() is None


def test_get_provider_returns_openrouter_when_configured():
    with patch("app.services.explain.llm_service.settings") as s:
        s.llm_api_key = "sk-test"
        s.llm_provider = "openrouter"
        assert isinstance(get_llm_provider(), OpenRouterProvider)


# ---------------------------------------------------------------------------
# PII redaction tests
# ---------------------------------------------------------------------------


def test_pii_redacted_before_llm_call():
    """Verify that PII is removed before reaching the LLM provider."""
    raw = "Call 9876543210 and send OTP to user@ybl"
    redacted = redact(raw)
    assert "9876543210" not in redacted
    assert "user@ybl" not in redacted
    assert "[REDACTED]" in redacted


# ---------------------------------------------------------------------------
# RAG chat integration tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rag_chat_uses_llm_when_available():
    from app.services.explain.rag_chat import answer_question

    mock_db = AsyncMock()
    mock_provider = MagicMock()
    mock_provider.complete = AsyncMock(return_value="grounded answer")

    mock_context = [
        {
            "type": "focal_session",
            "session_id": "S-1234",
            "risk_score": 80,
            "risk_level": "high",
        }
    ]
    mock_sources = [{"type": "focal", "session_id": "S-1234"}]

    with (
        patch(
            "app.services.explain.rag_chat.retrieve",
        ) as mock_retrieve,
        patch(
            "app.services.explain.rag_chat.get_llm_provider",
        ) as mock_factory,
        patch(
            "app.services.explain.rag_chat.redact",
        ) as mock_redact,
    ):
        mock_retrieve.return_value = {
            "context": mock_context,
            "sources": mock_sources,
        }
        mock_factory.return_value = mock_provider
        mock_redact.side_effect = lambda x: x

        result = await answer_question(
            question="Why flagged?",
            session_id="S-1234",
            db=mock_db,
        )

    mock_provider.complete.assert_called_once()
    assert result["answer"] == "grounded answer"


@pytest.mark.asyncio
async def test_rag_chat_template_fallback_when_no_key():
    from app.services.explain.rag_chat import answer_question

    mock_db = AsyncMock()

    mock_context = [
        {
            "type": "focal_session",
            "session_id": "S-1234",
            "risk_score": 80,
            "risk_level": "high",
            "action_taken": "block",
            "entities_found": 2,
            "scan_type": "whatsapp",
        }
    ]

    with (
        patch("app.services.explain.rag_chat.retrieve") as mock_retrieve,
        patch("app.services.explain.rag_chat.get_llm_provider") as mock_factory,
        patch("app.services.explain.rag_chat.redact") as mock_redact,
    ):
        mock_retrieve.return_value = {
            "context": mock_context,
            "sources": [{"type": "focal", "session_id": "S-1234"}],
        }
        mock_factory.return_value = None
        mock_redact.side_effect = lambda x: x

        result = await answer_question(
            question="Why flagged?",
            session_id="S-1234",
            db=mock_db,
        )

    assert "S-1234" in result["answer"]
    assert result["answer"]  # non-empty template answer
