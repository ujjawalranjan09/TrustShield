"""Provider-agnostic LLM service for grounded explainability answers."""

import logging
from abc import ABC, abstractmethod

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
You are TrustShield's explainability assistant. You answer ONLY from the \
provided context. Rules:

1. Cite sources using [S-session_id] notation.
2. If the context is insufficient to answer, say so explicitly.
3. NEVER invent risk factors, entities, or scores not present in the context.
4. NEVER include personally identifiable information (PII) in your answer.
"""


class LLMProvider(ABC):
    """Abstract base for LLM providers."""

    @abstractmethod
    async def complete(
        self,
        system: str,
        context: str,
        question: str,
        max_tokens: int = 512,
        temperature: float = 0.1,
    ) -> str:
        """Send a completion request and return the assistant message."""


class OpenRouterProvider(LLMProvider):
    """LLM provider using OpenRouter's chat completions API."""

    def __init__(self) -> None:
        self._api_key = settings.llm_api_key
        self._model = settings.llm_model
        self._timeout = settings.llm_timeout_seconds

    async def complete(
        self,
        system: str,
        context: str,
        question: str,
        max_tokens: int = 512,
        temperature: float = 0.1,
    ) -> str:
        user_msg = f"Context:\n{context}\n\nQuestion: {question}"
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self._model,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user_msg},
                    ],
                    "max_tokens": max_tokens,
                    "temperature": temperature,
                },
            )
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]


class LocalLLMProvider(LLMProvider):
    """LLM provider for local deployments (vLLM, Ollama, etc.)."""

    def __init__(self) -> None:
        self._base_url = settings.llm_base_url.rstrip("/")
        self._model = settings.llm_model
        self._timeout = settings.llm_timeout_seconds

    async def complete(
        self,
        system: str,
        context: str,
        question: str,
        max_tokens: int = 512,
        temperature: float = 0.1,
    ) -> str:
        user_msg = f"Context:\n{context}\n\nQuestion: {question}"
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.post(
                f"{self._base_url}/v1/chat/completions",
                headers={"Content-Type": "application/json"},
                json={
                    "model": self._model,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user_msg},
                    ],
                    "max_tokens": max_tokens,
                    "temperature": temperature,
                },
            )
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]


def get_llm_provider() -> LLMProvider | None:
    """Return the configured LLM provider, or None if unavailable."""
    if not settings.llm_api_key:
        logger.info("No LLM API key configured; using template fallback")
        return None
    if settings.llm_provider == "local":
        return LocalLLMProvider()
    return OpenRouterProvider()
