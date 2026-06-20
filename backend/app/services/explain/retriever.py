"""Retriever — fetches focal session data, neighbours, and attribution context.

Returns a ``{"context": [...], "sources": [...]}`` dict ready to be injected
into the explainability prompt.
"""

import json
import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.scan_event import ScanEvent
from app.services.explain.vector_store import find_similar_sessions

logger = logging.getLogger(__name__)


async def retrieve(
    question: str,
    session_id: str,
    db: AsyncSession,
    top_k: int = 5,
) -> dict[str, Any]:
    """Retrieve grounding context for an explainability question.

    1. Fetches the focal ``ScanEvent`` by *session_id*.
    2. Finds *top_k* similar sessions via the vector store.
    3. Collects attribution / entity data attached to the focal session.
    4. Returns ``{"context": [...tagged facts...], "sources": [...source ids...]}``.

    If *session_id* is not found the function returns an empty context
    (not an error).
    """
    result = await db.execute(
        select(ScanEvent).filter(ScanEvent.session_id == session_id)
    )
    focal = result.scalars().first()

    if not focal:
        return {"context": [], "sources": []}

    similar = await find_similar_sessions(session_id, db, top_k=top_k)

    context: list[dict] = []
    sources: list[dict] = []

    context.append({
        "type": "focal_session",
        "session_id": session_id,
        "risk_score": focal.risk_score,
        "risk_level": focal.risk_level,
        "action_taken": focal.action_taken,
        "entities_found": focal.entities_found,
        "scan_type": focal.scan_type,
    })
    sources.append({"type": "focal", "session_id": session_id})

    if focal.risk_score is not None:
        context.append({
            "type": "risk_factor",
            "label": "risk_score",
            "value": focal.risk_score,
            "session_id": session_id,
        })

    entities = _parse_json_attr(focal, "entities")
    if entities:
        context.append({
            "type": "entity_matches",
            "entities": entities,
            "session_id": session_id,
        })
        sources.append({"type": "entities", "session_id": session_id})

    attributions = _parse_json_attr(focal, "attributions")
    if attributions:
        context.append({
            "type": "attributions",
            "data": attributions,
            "session_id": session_id,
        })
        sources.append({"type": "attributions", "session_id": session_id})

    for sim in similar:
        context.append({
            "type": "similar_session",
            "session_id": sim["session_id"],
            "similarity": round(sim["similarity"], 4),
        })
        sources.append({
            "type": "similar",
            "session_id": sim["session_id"],
        })

    return {"context": context, "sources": sources}


def _parse_json_attr(obj: Any, attr: str) -> Any:
    """Return parsed JSON from a column that may be a JSON string or None."""
    val = getattr(obj, attr, None)
    if val is None:
        return None
    if isinstance(val, (list, dict)):
        return val
    try:
        return json.loads(val)
    except (json.JSONDecodeError, TypeError):
        return None
