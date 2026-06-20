"""Cross-cell reputation federation.

Fans out read-only, tokenized reputation queries to peer cells and aggregates
the results with recency weighting.  The entity value is tokenized before
leaving the cell — no raw PII crosses cell boundaries.

If federation is unavailable (peers down, network errors), the caller receives
local-only reputation with graceful degradation.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx

from app.config import settings
from app.services.security.pii_vault import tokenize

logger = logging.getLogger(__name__)

_FEDERATION_TIMEOUT_SECONDS = 5
_RECENCY_WINDOWS = [
    (7, 1.0),
    (30, 0.7),
    (90, 0.4),
    (180, 0.2),
]


def _parse_cell_urls() -> Dict[str, str]:
    raw = settings.cell_urls
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
        if not isinstance(parsed, dict):
            return {}
        return {str(k): str(v) for k, v in parsed.items()}
    except (json.JSONDecodeError, TypeError):
        return {}


def _recency_weight(last_seen: Optional[datetime]) -> float:
    if last_seen is None:
        return 0.1
    now = datetime.now(timezone.utc)
    if last_seen.tzinfo is None:
        last_seen = last_seen.replace(tzinfo=timezone.utc)
    days = (now - last_seen).days
    for window, weight in _RECENCY_WINDOWS:
        if days <= window:
            return weight
    return 0.1


async def _query_peer_cell(
    peer_url: str,
    tokenized_entity: str,
    entity_type: str,
    timeout: float = _FEDERATION_TIMEOUT_SECONDS,
) -> Optional[Dict[str, Any]]:
    """Send a read-only reputation query to a peer cell."""
    url = f"{peer_url.rstrip('/')}/api/v1/reputation/federated-lookup"
    try:
        async with httpx.AsyncClient(timeout=timeout, verify=True) as client:
            resp = await client.post(
                url,
                json={
                    "entity_value": tokenized_entity,
                    "entity_type": entity_type,
                    "federation_request": True,
                },
                headers={"X-Federation-Request": "true"},
            )
            if resp.status_code == 200:
                return resp.json()
            logger.warning(
                "Peer cell %s returned status %d for federated lookup",
                peer_url,
                resp.status_code,
            )
            return None
    except Exception as exc:
        logger.warning("Federation query to %s failed: %s", peer_url, exc)
        return None


def _aggregate_scores(
    local_score: int,
    local_last_seen: Optional[datetime],
    peer_scores: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Aggregate local + peer scores with recency weighting."""
    all_scores: List[Dict[str, Any]] = [{"score": local_score, "last_seen": local_last_seen, "source": "local"}]
    for ps in peer_scores:
        if ps.get("score") is not None:
            raw = ps.get("last_seen")
            if isinstance(raw, str):
                last_seen = datetime.fromisoformat(raw)
            elif isinstance(raw, datetime):
                last_seen = raw
            else:
                last_seen = None
            all_scores.append({
                "score": ps["score"],
                "last_seen": last_seen,
                "source": ps.get("source", "peer"),
            })

    if len(all_scores) <= 1:
        clamped = max(0, min(100, local_score))
        return {
            "score": clamped,
            "sources": ["local"],
            "peer_count": 0,
        }

    weighted_sum = 0.0
    weight_total = 0.0
    sources = []
    for entry in all_scores:
        w = _recency_weight(entry["last_seen"])
        weighted_sum += entry["score"] * w
        weight_total += w
        sources.append(entry["source"])

    aggregated = int(round(weighted_sum / weight_total)) if weight_total > 0 else local_score
    aggregated = max(0, min(100, aggregated))

    return {
        "score": aggregated,
        "sources": sources,
        "peer_count": len(all_scores) - 1,
    }


async def federated_reputation_lookup(
    entity_value: str,
    entity_type: str,
    db: Any,
) -> Dict[str, Any]:
    """Look up reputation locally, then fan out to peer cells.

    Returns aggregated reputation with recency weighting.
    Falls back to local-only if federation is unavailable.
    """
    from app.services.intel.reputation_service import compute_reputation

    local_result = await compute_reputation(entity_value, entity_type, db)

    cell_urls = _parse_cell_urls()
    peer_urls = [
        url for region, url in cell_urls.items()
        if region != settings.cell_region
    ]

    if not peer_urls:
        return {
            **local_result,
            "federation": {
                "peer_count": 0,
                "sources": ["local"],
            },
        }

    tokenized_entity = tokenize(entity_value, entity_type)

    peer_tasks = [
        _query_peer_cell(url, tokenized_entity, entity_type)
        for url in peer_urls
    ]
    peer_results = await asyncio.gather(*peer_tasks, return_exceptions=True)

    peer_scores: List[Dict[str, Any]] = []
    for i, result in enumerate(peer_results):
        if isinstance(result, Exception):
            logger.warning("Federation to %s raised: %s", peer_urls[i], result)
            continue
        if result is not None:
            result["source"] = peer_urls[i]
            peer_scores.append(result)

    aggregated = _aggregate_scores(
        local_result.get("score", 0),
        (
            datetime.fromisoformat(local_result["last_reported_at"])
            if local_result.get("last_reported_at")
            else None
        ),
        peer_scores,
    )

    return {
        **local_result,
        "score": aggregated["score"],
        "federation": {
            "peer_count": aggregated["peer_count"],
            "sources": aggregated["sources"],
        },
    }


async def federation_health_check() -> Dict[str, Any]:
    """Check the status of each peer cell."""
    cell_urls = _parse_cell_urls()
    peers = {
        region: url
        for region, url in cell_urls.items()
        if region != settings.cell_region
    }

    if not peers:
        return {
            "local_region": settings.cell_region,
            "peers": {},
            "all_healthy": True,
        }

    statuses: Dict[str, Dict[str, Any]] = {}

    async def _check_peer(region: str, url: str) -> None:
        try:
            async with httpx.AsyncClient(timeout=5, verify=True) as client:
                resp = await client.get(f"{url.rstrip('/')}/health")
                statuses[region] = {
                    "url": url,
                    "healthy": resp.status_code == 200,
                    "status_code": resp.status_code,
                }
        except Exception as exc:
            statuses[region] = {
                "url": url,
                "healthy": False,
                "error": str(exc),
            }

    await asyncio.gather(*[_check_peer(r, u) for r, u in peers.items()])

    all_healthy = all(s.get("healthy", False) for s in statuses.values())

    return {
        "local_region": settings.cell_region,
        "peers": statuses,
        "all_healthy": all_healthy,
    }
