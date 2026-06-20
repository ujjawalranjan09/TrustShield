"""Risk propagation via Personalized PageRank on the entity graph.

Computes risk scores by propagating from known bad actors through the
entity relationship graph. Runs as a Celery task every 6 hours.
"""

import asyncio
import hashlib
import logging
from collections import deque
from typing import Any, Dict, List, Set, Tuple

from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)

DAMPING = 0.85
ITERATIONS = 20
BLACKLIST_THRESHOLD = 5  # min report_count to be a seed


def _hash_value(value: str) -> str:
    return hashlib.sha256(value.lower().strip().encode()).hexdigest()[:16]


def propagate_belief(
    graph: Dict[str, List[Tuple[str, float]]],
    entity_value: str,
    seeds: Set[str] = None,
    max_hops: int = 3,
    dampening: float = 0.7,
) -> float:
    """Belief-propagation-style risk propagation — proximity to fraud seeds.

    Computes how close ``entity_value`` is to any confirmed-bad entity
    (``seeds``). BFS walks up to ``max_hops`` outward; each seed reached
    at hop *h* contributes ``dampening^h * edge_weight``.

    Args:
        graph: Adjacency dict mapping entity_value -> [(neighbor_value, edge_weight)].
               edge_weight should be in [0, 1].
        entity_value: Target entity to evaluate.
        seeds: Set of known-bad entity values. If the entity itself is a
               seed, returns 0.0 (it IS fraud, no propagation needed).
        max_hops: Maximum BFS depth (default 3).
        dampening: Decay factor per hop (default 0.7).

    Returns:
        Accumulated propagated_risk in [0, 1], clamped.
    """
    if seeds is None:
        seeds = set()
    if entity_value in seeds:
        return 0.0
    if entity_value not in graph:
        return 0.0

    visited: Set[str] = {entity_value}
    queue: deque = deque()
    queue.append((entity_value, 0))
    total_risk = 0.0

    while queue:
        node, hop = queue.popleft()
        if hop >= max_hops:
            continue
        for neighbor, edge_weight in graph.get(node, []):
            if neighbor in visited:
                continue
            visited.add(neighbor)
            if neighbor in seeds:
                total_risk += dampening ** hop * edge_weight
            queue.append((neighbor, hop + 1))

    return min(1.0, max(0.0, total_risk))


async def _propagate_risk_scores() -> Dict[str, Any]:
    """Run Personalized PageRank across the Neo4j entity graph."""
    from app.services.graph.entity_graph import FraudEntityGraph

    graph = FraudEntityGraph()
    try:
        if not graph.connected:
            return {"status": "skipped", "reason": "Neo4j not connected"}

        entities = await graph.get_all_entities()
        if not entities:
            return {"status": "success", "nodes_updated": 0, "max_score_delta": 0}

        # Build adjacency for PageRank
        entity_map = {e["value"]: e for e in entities}
        n = len(entities)
        value_to_idx = {e["value"]: i for i, e in enumerate(entities)}

        # Get all edges
        edges = await _get_all_edges(graph)
        adj: Dict[int, List[int]] = {i: [] for i in range(n)}
        for src, dst in edges:
            if src in value_to_idx and dst in value_to_idx:
                si, di = value_to_idx[src], value_to_idx[dst]
                adj[si].append(di)
                adj[di].append(si)

        # Seed: entities with report_count >= threshold
        seeds = set()
        for e in entities:
            if e.get("report_count", 0) >= BLACKLIST_THRESHOLD:
                seeds.add(value_to_idx[e["value"]])

        # Personalized PageRank
        scores = [1.0 / n] * n
        if seeds:
            seed_scores = {i: 1.0 / len(seeds) for i in seeds}
        else:
            seed_scores = {i: 1.0 / n for i in range(n)}

        for _ in range(ITERATIONS):
            new_scores = [(1 - DAMPING) / n] * n
            for i in range(n):
                if adj[i]:
                    share = scores[i] / len(adj[i])
                    for j in adj[i]:
                        new_scores[j] += DAMPING * share
            # Add personalization
            for i in range(n):
                new_scores[i] += DAMPING * seed_scores.get(i, 0) * (1 - DAMPING)
            scores = new_scores

        # Compute risk scores (normalize to 0-1)
        max_score = max(scores) if scores else 1.0
        min_score = min(scores)
        score_range = max_score - min_score if max_score > min_score else 1.0

        # Build adjacency dict for belief propagation
        belief_adj: Dict[str, List[Tuple[str, float]]] = {e["value"]: [] for e in entities}
        for src, dst in edges:
            if src in belief_adj and dst in belief_adj:
                weight = 0.5
                belief_adj[src].append((dst, weight))
                belief_adj[dst].append((src, weight))

        # Seed risk: entities with report_count >= threshold get high base risk
        seed_entities = {e["value"] for e in entities if e.get("report_count", 0) >= BLACKLIST_THRESHOLD}

        updates = []
        for i, e in enumerate(entities):
            normalized = (scores[i] - min_score) / score_range
            base_risk = e.get("graph_risk_score", 0)
            new_risk = min(1.0, base_risk * 0.6 + normalized * 0.4)

            # Compute propagated_risk via belief propagation
            if e["value"] in seed_entities:
                prop_risk = 1.0
            else:
                prop_risk = propagate_belief(
                    belief_adj, e["value"], seeds=seed_entities, max_hops=3, dampening=0.7,
                )

            updates.append({
                "value": e["value"],
                "pagerank": round(normalized, 6),
                "risk": round(new_risk, 6),
                "propagated_risk": round(prop_risk, 6),
            })

        await graph.update_entity_scores(updates)

        max_delta = max(abs(u["risk"] - entity_map[u["value"]].get("graph_risk_score", 0))
                       for u in updates) if updates else 0

        logger.info("PageRank complete: %d nodes, max_delta=%.4f", len(updates), max_delta)
        return {
            "status": "success",
            "nodes_updated": len(updates),
            "max_score_delta": round(max_delta, 4),
        }
    finally:
        await graph.close()


async def _get_all_edges(graph) -> List[Tuple[str, str]]:
    """Get all APPEARED_WITH edges from Neo4j."""
    if not graph.connected or not graph.driver:
        return []
    query = "MATCH (a:Entity)-[r:APPEARED_WITH]-(b:Entity) RETURN a.value AS src, b.value AS dst"
    edges = []
    try:
        async with graph.driver.session() as session:
            result = await session.run(query)
            async for record in result:
                edges.append((record["src"], record["dst"]))
    except Exception as e:
        logger.error("Failed to fetch edges: %s", e)
    return edges


@celery_app.task(name="app.services.graph.risk_propagation.propagate_risk_scores")
def propagate_risk_scores() -> Dict[str, Any]:
    """Celery task wrapper for risk score propagation."""
    return asyncio.run(_propagate_risk_scores())


if __name__ == "__main__":
    propagate_risk_scores()
