"""Grounding evaluation harness — verifies LLM answers don't hallucinate.

Requires RUN_RAG_EVAL=1 to run (skipped by default).
"""

import json
import os
import re
from pathlib import Path
from unittest.mock import MagicMock

import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_RAG_EVAL") != "1",
    reason="Set RUN_RAG_EVAL=1 to run grounding evaluation",
)

EVAL_FILE = Path(__file__).resolve().parents[2] / "ml" / "data" / "explain_eval.jsonl"


def _load_cases():
    cases = []
    with open(EVAL_FILE) as f:
        for line in f:
            line = line.strip()
            if line:
                cases.append(json.loads(line))
    return cases


def _mock_llm_answer(answer_text: str):
    """Return a mock get_llm_provider that yields *answer_text*."""
    provider = MagicMock()

    async def _complete(system, context, question, max_tokens=512, temperature=0.1):
        return answer_text

    provider.complete = _complete
    return provider


def _context_text(session_ids: list[str]) -> str:
    parts = []
    for sid in session_ids:
        parts.append(f"Session {sid}: risk_score=75, risk_level=high")
    return "\n".join(parts)


def _extract_session_ids(text: str) -> set[str]:
    return set(re.findall(r"S-\d+", text))


def _mock_retriever(context_session_ids: list[str]):
    """Return a mock retrieve function that returns context for given session ids."""
    ctx = [
        {
            "type": "focal_session",
            "session_id": sid,
            "risk_score": 75,
            "risk_level": "high",
        }
        for sid in context_session_ids
    ]
    sources = [{"type": "focal", "session_id": sid} for sid in context_session_ids]

    async def retrieve(question, session_id, db, top_k=5):
        return {"context": ctx, "sources": sources}

    return retrieve


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_grounding_no_hallucinated_session_ids():
    """LLM cites a fabricated session id not in context -> FAIL."""
    cases = _load_cases()
    assert cases, "No eval cases found"

    case = cases[0]
    fabricated_answer = "Session S-9999 shows unusual activity. See [S-9999]."
    retrieved_ids = case["expected_source_ids"]

    cited = _extract_session_ids(fabricated_answer)
    hallucinated = cited - set(retrieved_ids)
    assert hallucinated, "Expected hallucinated session ids but LLM answer was clean"


def test_grounding_cites_only_retrieved():
    """LLM cites only sessions in context -> PASS."""
    cases = _load_cases()
    assert cases, "No eval cases found"

    case = cases[0]
    clean_answer = f"Session {case['focal_session']} was flagged. See [S-1234]."
    # Simulate that S-1234 was actually retrieved alongside the focal
    all_retrieved = case["expected_source_ids"] + ["S-1234"]

    cited = _extract_session_ids(clean_answer)
    hallucinated = cited - set(all_retrieved)
    assert not hallucinated, f"Hallucinated session ids: {hallucinated}"


def test_grounding_forbidden_claims():
    """LLM output contains a forbidden claim -> FAIL."""
    cases = _load_cases()
    assert cases, "No eval cases found"

    case = cases[1]
    forbidden = case["forbidden_claims"]
    llm_output = f"Session {case['focal_session']}: risk is high. {forbidden[0].title()}."

    violations = [claim for claim in forbidden if claim.lower() in llm_output.lower()]
    assert violations, "Expected forbidden claim violations but none found"
