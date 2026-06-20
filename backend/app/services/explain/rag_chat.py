"""Explainability chat — RAG with optional LLM grounding."""

import logging
from typing import Dict, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.explain.llm_service import SYSTEM_PROMPT, get_llm_provider
from app.services.explain.retriever import retrieve
from app.utils.pii import redact

logger = logging.getLogger(__name__)


async def answer_question(
    question: str,
    session_id: Optional[str],
    db: AsyncSession,
) -> Dict:
    """Answer an explainability question using session data + attributions."""
    if not session_id:
        return {
            "answer": "Please provide a session_id to analyze. Example: 'Why was session S-1234 flagged?'",
            "sources": [],
            "context_ids": [],
        }

    data = await retrieve(question, session_id, db)

    if not data["context"]:
        return {
            "answer": f"Session {session_id} not found. Please check the session ID.",
            "sources": [],
            "context_ids": [],
        }

    context_text = _format_context(data["context"])
    redacted_question = redact(question)
    redacted_context = redact(context_text)

    provider = get_llm_provider()
    if provider:
        answer = await provider.complete(
            system=SYSTEM_PROMPT,
            context=redacted_context,
            question=redacted_question,
        )
        context_ids = _extract_cited_ids(answer)
        return {
            "answer": answer,
            "sources": data["sources"],
            "context_ids": context_ids,
        }

    answer = _template_answer(session_id, data["context"], data["sources"])
    return {"answer": answer, "sources": data["sources"], "context_ids": []}


def _format_context(context: list[dict]) -> str:
    parts = []
    for item in context:
        if item["type"] == "focal_session":
            parts.append(
                f"[S-{item['session_id']}] Focal session: risk_score={item.get('risk_score')}, "
                f"risk_level={item.get('risk_level')}, action={item.get('action_taken', 'N/A')}, "
                f"entities_found={item.get('entities_found', 0)}, scan_type={item.get('scan_type', 'N/A')}"
            )
        elif item["type"] == "similar_session":
            parts.append(
                f"[S-{item['session_id']}] Similar session (similarity={item.get('similarity')})"
            )
        elif item["type"] == "entity_matches":
            parts.append(
                f"[S-{item['session_id']}] Entities: {item.get('entities')}"
            )
        elif item["type"] == "attributions":
            parts.append(
                f"[S-{item['session_id']}] Attributions: {item.get('data')}"
            )
        else:
            parts.append(f"[S-{item.get('session_id', 'unknown')}] {item}")
    return "\n".join(parts)


def _extract_cited_ids(answer: str) -> list[str]:
    import re
    return list(set(re.findall(r"S-\d+", answer)))


def _template_answer(
    session_id: str, context: list[dict], sources: list[dict]
) -> str:
    focal = next(
        (c for c in context if c["type"] == "focal_session"), None
    )

    reasons: list[str] = []
    if focal:
        reasons.append(
            f"Risk score: {focal['risk_score']}/100 ({focal['risk_level']})"
        )
        if focal.get("action_taken"):
            reasons.append(
                f"Recommended action: {focal['action_taken'].replace('_', ' ').title()}"
            )
        if focal.get("entities_found") and focal["entities_found"] > 0:
            reasons.append(
                f"{focal['entities_found']} suspicious entity/entities were detected in the message"
            )
        if focal.get("scan_type"):
            reasons.append(f"Analysis type: {focal['scan_type']}")

    similar_count = sum(
        1 for c in context if c["type"] == "similar_session"
    )
    if similar_count:
        reasons.append(
            f"{similar_count} similar historical session(s) found via vector similarity"
        )

    if reasons:
        answer = (
            f"Session {session_id} was analyzed and resulted in a "
            f"{focal['risk_level'].upper() if focal else 'UNKNOWN'} risk "
            f"classification because:\n"
        )
        for i, reason in enumerate(reasons, 1):
            answer += f"{i}. {reason}\n"
    else:
        answer = (
            f"Session {session_id} was analyzed but limited information is available."
        )

    return answer
