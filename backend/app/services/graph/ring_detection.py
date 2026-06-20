"""Fraud ring detection via community detection on the entity graph.

Runs Louvain community detection (via networkx fallback or Neo4j GDS),
identifies fraud rings, and auto-files InvestigationCases for critical rings.
"""

import asyncio
import logging
import uuid
from collections import Counter
from typing import Any, Dict, List, Set

from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)

MIN_RING_SIZE = 5
MIN_REPORT_DENSITY = 0.5


async def _get_all_edges(graph) -> List[tuple]:
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


async def _detect_rings() -> Dict[str, Any]:
    """Detect fraud rings using community detection."""
    from app.services.graph.entity_graph import FraudEntityGraph

    graph = FraudEntityGraph()
    try:
        if not graph.connected:
            return {"status": "skipped", "reason": "Neo4j not connected"}

        entities = await graph.get_all_entities()
        if len(entities) < MIN_RING_SIZE:
            return {"status": "success", "rings_found": 0, "reason": "too few entities"}

        edges = await _get_all_edges(graph)

        # Build networkx graph for community detection
        try:
            import networkx as nx
            from networkx.algorithms.community import louvain_communities

            G = nx.Graph()
            for e in entities:
                G.add_node(e["value"], **e)
            for src, dst in edges:
                if G.has_node(src) and G.has_node(dst):
                    G.add_edge(src, dst)

            communities = louvain_communities(G, seed=42)
        except ImportError:
            logger.warning("networkx not installed, using simple clustering")
            communities = _simple_clustering(entities, edges)

        # Filter: only communities that pass the false-positive guard
        rings = []
        ring_assignments: Dict[str, str] = {}

        for i, community in enumerate(communities):
            if len(community) < MIN_RING_SIZE:
                continue

            members = [e for e in entities if e["value"] in community]
            reported = sum(1 for m in members if m.get("report_count", 0) > 0)
            report_density = reported / len(members) if members else 0

            if report_density < MIN_REPORT_DENSITY:
                continue

            ring_id = f"ring-{uuid.uuid4().hex[:8]}"
            total_reports = sum(m.get("report_count", 0) for m in members)
            scam_types = [m.get("entity_type", "unknown") for m in members]
            top_scam = Counter(scam_types).most_common(1)[0][0] if scam_types else "unknown"
            avg_pagerank = sum(m.get("pagerank_score", 0) for m in members) / len(members)

            risk_level = "critical" if total_reports >= 50 and len(members) >= 10 else \
                         "high" if total_reports >= 20 else \
                         "medium" if total_reports >= 5 else "low"

            rings.append({
                "ring_id": ring_id,
                "entity_count": len(members),
                "total_reports": total_reports,
                "top_scam_type": top_scam,
                "risk_level": risk_level,
                "avg_pagerank": avg_pagerank,
            })

            for m in members:
                ring_assignments[m["value"]] = ring_id

        # Write ring_id back to Neo4j
        await graph.update_ring_ids(ring_assignments)

        # Write FraudRing records + auto-file InvestigationCases
        await _persist_rings(rings)

        logger.info("Ring detection: %d rings found from %d entities", len(rings), len(entities))
        return {"status": "success", "rings_found": len(rings), "entities": len(entities)}
    finally:
        await graph.close()


def _simple_clustering(entities: List[Dict], edges: List[tuple]) -> List[Set[str]]:
    """Simple connected-component clustering as fallback when networkx unavailable."""
    adj: Dict[str, Set[str]] = {e["value"]: set() for e in entities}
    for src, dst in edges:
        if src in adj and dst in adj:
            adj[src].add(dst)
            adj[dst].add(src)

    visited: Set[str] = set()
    components: List[Set[str]] = []
    for node in adj:
        if node not in visited:
            component = set()
            stack = [node]
            while stack:
                n = stack.pop()
                if n in visited:
                    continue
                visited.add(n)
                component.add(n)
                stack.extend(adj[n] - visited)
            components.append(component)
    return components


async def _persist_rings(rings: List[Dict]) -> None:
    """Write FraudRing records and auto-file InvestigationCases."""
    from sqlalchemy import select
    from app.database import AsyncSessionLocal
    from app.models.ring import FraudRing
    from app.models.investigation import InvestigationCase

    async with AsyncSessionLocal() as db:
        for ring in rings:
            existing = await db.execute(
                select(FraudRing).filter(FraudRing.ring_id == ring["ring_id"])
            )
            if existing.scalars().first():
                continue

            fraud_ring = FraudRing(
                ring_id=ring["ring_id"],
                entity_count=ring["entity_count"],
                total_reports=ring["total_reports"],
                top_scam_type=ring["top_scam_type"],
                risk_level=ring["risk_level"],
                avg_pagerank=int(ring["avg_pagerank"] * 100),
            )
            db.add(fraud_ring)

            # Auto-file InvestigationCase for critical rings
            if ring["risk_level"] == "critical":
                case = InvestigationCase(
                    case_id=str(uuid.uuid4()),
                    ring_id=ring["ring_id"],
                    source="ring_detection",
                    priority="critical",
                    summary=f"Auto-detected fraud ring: {ring['entity_count']} entities, "
                            f"{ring['total_reports']} reports, type={ring['top_scam_type']}",
                )
                db.add(case)

        await db.commit()


@celery_app.task(name="app.services.graph.ring_detection.detect_fraud_rings")
def detect_fraud_rings() -> Dict[str, Any]:
    """Celery task for fraud ring detection."""
    return asyncio.run(_detect_rings())


if __name__ == "__main__":
    detect_fraud_rings()
