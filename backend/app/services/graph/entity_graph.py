"""Entity graph module with Neo4j + Redis cache.

Provides graph operations for fraud entity relationships with:
- Neo4j for persistent graph storage with proper indexes
- Redis for hot-path risk score caching
- PII-safe cache keys (hashed values)
- PII invariant: warns if raw PII appears in Cypher params
- Backpressure: buffers writes to Redis on Neo4j failure
"""

import hashlib
import json
import logging
import re
from typing import Any, Dict, List, Optional

from pydantic import BaseModel

from app.config import NEO4J_URI, NEO4J_PASSWORD, NEO4J_USER, REDIS_URL
from app.utils.pii import contains_pii

logger = logging.getLogger(__name__)

GRAPH_BACKLOG_KEY = "graph_backlog"

try:
    from neo4j import AsyncGraphDatabase
    _neo4j_available = True
except ImportError:
    _neo4j_available = False
    logger.warning("neo4j package not installed — graph features disabled")

try:
    import redis.asyncio as aioredis
    _redis_available = True
except ImportError:
    _redis_available = False


class FlaggedEntity(BaseModel):
    value: str
    entity_type: str
    report_count: int = 0
    graph_risk_score: float = 0.0


def _hash_value(value: str) -> str:
    """Hash entity value for safe Redis keys (no PII in keys)."""
    return hashlib.sha256(value.lower().strip().encode()).hexdigest()[:16]


class FraudEntityGraph:
    """Neo4j-backed graph with Redis risk-score cache."""

    def __init__(self) -> None:
        self.driver: Optional[Any] = None
        self.redis: Optional[Any] = None
        self.connected: bool = False
        self._connection_attempted: bool = False
        # Don't connect in constructor - do it lazily

    async def _connect(self) -> None:
        if self._connection_attempted:
            return
        self._connection_attempted = True
        
        if not _neo4j_available:
            return
        try:
            self.driver = AsyncGraphDatabase.driver(
                NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD),
                max_connection_lifetime=30,
                connection_timeout=2,
                max_transaction_retry_time=5
            )
            # Verify connection
            await self.driver.verify_connectivity()
            self.connected = True
            logger.info("Connected to Neo4j at %s", NEO4J_URI)
        except Exception as e:
            logger.warning("Failed to connect to Neo4j: %s", e)
            self.connected = False
            self.driver = None

        if _redis_available:
            try:
                self.redis = aioredis.from_url(REDIS_URL, decode_responses=True, socket_timeout=2)
                await self.redis.ping()
                logger.info("Redis connected for graph cache")
            except Exception as e:
                logger.warning("Redis unavailable for graph cache: %s", e)
                self.redis = None

    async def ensure_indexes(self) -> None:
        """Create indexes and constraints (idempotent)."""
        await self._ensure_connected()
        if not self.connected or not self.driver:
            return
        indexes = [
            "CREATE INDEX entity_value_idx IF NOT EXISTS FOR (n:Entity) ON (n.value)",
            "CREATE INDEX entity_type_idx IF NOT EXISTS FOR (n:Entity) ON (n.entity_type)",
            "CREATE INDEX entity_risk_idx IF NOT EXISTS FOR (n:Entity) ON (n.graph_risk_score)",
            "CREATE INDEX entity_ring_idx IF NOT EXISTS FOR (n:Entity) ON (n.ring_id)",
            "CREATE INDEX appeared_with_session IF NOT EXISTS FOR ()-[r:APPEARED_WITH]-() ON (r.session_id)",
        ]
        constraints = [
            "CREATE CONSTRAINT entity_unique IF NOT EXISTS FOR (n:Entity) REQUIRE n.value IS UNIQUE",
        ]
        try:
            async with self.driver.session() as session:
                for stmt in indexes + constraints:
                    await session.run(stmt)
            logger.info("Neo4j indexes/constraints ensured")
        except Exception as e:
            logger.error("Failed to create Neo4j indexes: %s", e)

    async def _ensure_connected(self) -> None:
        """Ensure connection is attempted before any graph operation."""
        if not self._connection_attempted:
            await self._connect()

    @staticmethod
    def _validate_no_raw_pii(params: dict) -> None:
        """Log a warning if raw PII patterns appear in Cypher parameters.

        This is a soft invariant: it documents the rule but never blocks.
        """
        for key, value in params.items():
            if isinstance(value, str) and contains_pii(value):
                logger.warning(
                    "Raw PII detected in Cypher param '%s' — "
                    "values should be tokenized before graph storage",
                    key,
                )

    async def _buffer_to_backlog(self, method: str, payload: dict) -> None:
        """Push a failed write to the Redis graph_backlog list."""
        if not self.redis:
            return
        try:
            event = json.dumps({"method": method, "payload": payload})
            await self.redis.lpush(GRAPH_BACKLOG_KEY, event)
            logger.info("Buffered %s event to graph_backlog", method)
        except Exception as e:
            logger.error("Failed to buffer to graph_backlog: %s", e)

    async def drain_backlog(self) -> int:
        """Retry all buffered events from graph_backlog. Returns count drained."""
        if not self.redis or not self.connected or not self.driver:
            return 0
        drained = 0
        while True:
            try:
                raw = await self.redis.rpop(GRAPH_BACKLOG_KEY)
                if not raw:
                    break
                event = json.loads(raw)
                method = event.get("method")
                payload = event.get("payload", {})
                if method == "add_entity":
                    entity = FlaggedEntity(**payload)
                    await self._add_entity_raw(entity)
                elif method == "add_session_link":
                    await self._add_session_link_raw(
                        payload["entity_a_id"],
                        payload["entity_b_id"],
                        payload["session_id"],
                    )
                drained += 1
            except Exception as e:
                logger.error("Failed to drain graph_backlog event: %s", e)
                break
        if drained:
            logger.info("Drained %d events from graph_backlog", drained)
        return drained

    async def add_entity(self, entity: FlaggedEntity) -> None:
        """Upsert an entity node with enriched properties."""
        self._validate_no_raw_pii({"value": entity.value, "type": entity.entity_type})
        await self._ensure_connected()
        if not self.connected or not self.driver:
            return
        await self._add_entity_raw(entity)

    async def _add_entity_raw(self, entity: FlaggedEntity) -> None:
        """Execute the MERGE write for an entity (no PII re-check)."""
        query = """
        MERGE (n:Entity {value: $value})
        ON CREATE SET n.entity_type = $type, n.report_count = $report_count,
                      n.first_seen = timestamp(), n.last_seen = timestamp(),
                      n.graph_risk_score = $graph_risk_score,
                      n.pagerank_score = 0.0, n.ring_id = null,
                      n.last_risk_update = timestamp()
        ON MATCH SET n.report_count = n.report_count + 1, n.last_seen = timestamp(),
                    n.graph_risk_score = CASE WHEN $graph_risk_score > n.graph_risk_score
                                              THEN $graph_risk_score ELSE n.graph_risk_score END
        """
        params = {
            "value": entity.value,
            "type": entity.entity_type,
            "report_count": entity.report_count,
            "graph_risk_score": entity.graph_risk_score,
        }
        try:
            async with self.driver.session() as session:
                await session.run(query, **params)
            await self._invalidate_cache(entity.value)
        except Exception as e:
            logger.error("Neo4j add_entity failed: %s", e)
            await self._buffer_to_backlog("add_entity", entity.model_dump())

    async def add_session_link(
        self, entity_a_id: str, entity_b_id: str, session_id: str
    ) -> None:
        """Create an APPEARED_WITH relationship between two entities."""
        self._validate_no_raw_pii({
            "entity_a_id": entity_a_id,
            "entity_b_id": entity_b_id,
            "session_id": session_id,
        })
        await self._ensure_connected()
        if not self.connected or not self.driver:
            return
        await self._add_session_link_raw(entity_a_id, entity_b_id, session_id)

    async def _add_session_link_raw(
        self, entity_a_id: str, entity_b_id: str, session_id: str
    ) -> None:
        """Execute the session-link write (no PII re-check)."""
        query = """
        MATCH (a:Entity {value: $a_val}), (b:Entity {value: $b_val})
        MERGE (a)-[r:APPEARED_WITH {session_id: $session_id}]-(b)
        ON CREATE SET r.timestamp = timestamp(), r.weight = 1
        ON MATCH SET r.weight = r.weight + 1
        """
        params = {"a_val": entity_a_id, "b_val": entity_b_id, "session_id": session_id}
        try:
            async with self.driver.session() as session:
                await session.run(query, **params)
        except Exception as e:
            logger.error("Neo4j add_session_link failed: %s", e)
            await self._buffer_to_backlog("add_session_link", params)

    async def get_entity_risk(self, entity_value: str) -> float:
        """Get risk score with Redis cache → Neo4j fallback."""
        await self._ensure_connected()
        cache_key = f"graph:risk:{_hash_value(entity_value)}"

        if self.redis:
            try:
                cached = await self.redis.get(cache_key)
                if cached is not None:
                    return float(cached)
            except Exception:
                pass

        score = await self._compute_entity_risk(entity_value)

        if self.redis and score > 0:
            try:
                await self.redis.setex(cache_key, 21600, str(score))
            except Exception:
                pass

        return score

    async def _compute_entity_risk(self, entity_value: str) -> float:
        if not self.connected or not self.driver:
            return 0.0
        query = """
        MATCH (n:Entity {value: $value})
        OPTIONAL MATCH (n)--(m)
        RETURN n.graph_risk_score AS base_score, n.pagerank_score AS pagerank,
               count(m) AS degree
        """
        try:
            async with self.driver.session() as session:
                result = await session.run(query, value=entity_value)
                record = await result.single()
                if record:
                    base = record["base_score"] or 0.0
                    pagerank = record["pagerank"] or 0.0
                    degree = record["degree"] or 0
                    connection_boost = min(0.3, degree * 0.05)
                    return min(1.0, base + pagerank * 0.3 + connection_boost)
            return 0.0
        except Exception as e:
            logger.error("Neo4j get_entity_risk failed: %s", e)
            return 0.0

    async def _invalidate_cache(self, entity_value: str) -> None:
        if self.redis:
            try:
                await self.redis.delete(f"graph:risk:{_hash_value(entity_value)}")
            except Exception:
                pass

    async def invalidate_all_risk_cache(self) -> int:
        """Invalidate all risk cache entries (called after propagation)."""
        if not self.redis:
            return 0
        try:
            keys = []
            async for key in self.redis.scan_iter("graph:risk:*"):
                keys.append(key)
            if keys:
                await self.redis.delete(*keys)
            return len(keys)
        except Exception:
            return 0

    async def get_neighbors(self, entity_value: str, depth: int = 2) -> List[Dict[str, Any]]:
        """Get entities connected within depth hops."""
        await self._ensure_connected()
        if not self.connected or not self.driver:
            return []
        query = """
        MATCH (n:Entity {value: $value})-[*1..$depth]-(m)
        RETURN DISTINCT m.value AS value, m.entity_type AS entity_type,
               m.graph_risk_score AS risk_score, m.pagerank_score AS pagerank,
               m.ring_id AS ring_id, m.report_count AS report_count
        """
        try:
            async with self.driver.session() as session:
                result = await session.run(query, value=entity_value, depth=depth)
                return [dict(record) async for record in result]
        except Exception as e:
            logger.error("Neo4j get_neighbors failed: %s", e)
            return []

    async def get_graph_for_visualization(
        self, entity_value: str, depth: int = 2, mask_pii: bool = True
    ) -> Dict[str, Any]:
        """Return Cytoscape-compatible graph JSON."""
        await self._connect()  # Lazy connection
        if not self.connected:
            return {"nodes": [], "edges": []}
        
        neighbors = await self.get_neighbors(entity_value, depth)

        # Add center entity
        center_risk = await self.get_entity_risk(entity_value)
        center_id = _hash_value(entity_value) if mask_pii else entity_value
        label = entity_value[:8] + "..." if mask_pii else entity_value

        nodes = [{
            "data": {
                "id": center_id,
                "label": label,
                "risk": center_risk,
                "entity_type": "CENTER",
                "ring_id": None,
                "report_count": 0,
            }
        }]

        edges = []
        seen = {center_id}

        for n in neighbors:
            nid = _hash_value(n["value"]) if mask_pii else n["value"]
            if nid in seen:
                continue
            seen.add(nid)
            nlabel = n["value"][:8] + "..." if mask_pii else n["value"]
            nodes.append({
                "data": {
                    "id": nid,
                    "label": nlabel,
                    "risk": n.get("risk_score", 0),
                    "entity_type": n.get("entity_type", "UNKNOWN"),
                    "ring_id": n.get("ring_id"),
                    "report_count": n.get("report_count", 0),
                }
            })
            edges.append({
                "data": {
                    "source": center_id,
                    "target": nid,
                    "label": "APPEARED_WITH",
                }
            })

        return {"nodes": nodes, "edges": edges}

    async def get_all_entities(self) -> List[Dict[str, Any]]:
        """Get all entity nodes (for propagation)."""
        await self._ensure_connected()
        if not self.connected or not self.driver:
            return []
        query = """
        MATCH (n:Entity)
        RETURN n.value AS value, n.entity_type AS entity_type,
               n.report_count AS report_count, n.graph_risk_score AS graph_risk_score,
               n.pagerank_score AS pagerank_score
        """
        try:
            async with self.driver.session() as session:
                result = await session.run(query)
                return [dict(record) async for record in result]
        except Exception as e:
            logger.error("Neo4j get_all_entities failed: %s", e)
            return []

    async def update_entity_scores(self, updates: List[Dict[str, Any]]) -> None:
        """Bulk update pagerank and risk scores."""
        await self._ensure_connected()
        if not self.connected or not self.driver or not updates:
            return
        query = """
        UNWIND $updates AS u
        MATCH (n:Entity {value: u.value})
        SET n.pagerank_score = u.pagerank,
            n.graph_risk_score = u.risk,
            n.last_risk_update = timestamp()
        """
        try:
            async with self.driver.session() as session:
                await session.run(query, updates=updates)
            await self.invalidate_all_risk_cache()
        except Exception as e:
            logger.error("Neo4j update_entity_scores failed: %s", e)

    async def update_ring_ids(self, ring_assignments: Dict[str, str]) -> None:
        """Bulk update ring_id on entities."""
        await self._ensure_connected()
        if not self.connected or not self.driver or not ring_assignments:
            return
        updates = [{"value": v, "ring_id": r} for v, r in ring_assignments.items()]
        query = """
        UNWIND $updates AS u
        MATCH (n:Entity {value: u.value})
        SET n.ring_id = u.ring_id
        """
        try:
            async with self.driver.session() as session:
                await session.run(query, updates=updates)
        except Exception as e:
            logger.error("Neo4j update_ring_ids failed: %s", e)

    async def get_entity_detail(
        self, entity_value: str, mask_pii: bool = True
    ) -> Optional[Dict[str, Any]]:
        """Get a single entity node with its full properties."""
        await self._ensure_connected()
        if not self.connected or not self.driver:
            return None
        query = """
        MATCH (n:Entity {value: $value})
        RETURN n.value AS value, n.entity_type AS entity_type,
               n.graph_risk_score AS risk_score, n.pagerank_score AS pagerank,
               n.ring_id AS ring_id, n.report_count AS report_count,
               n.first_seen AS first_seen, n.last_seen AS last_seen
        """
        try:
            async with self.driver.session() as session:
                result = await session.run(query, value=entity_value)
                record = await result.single()
                if record:
                    return dict(record)
            return None
        except Exception as e:
            logger.error("Neo4j get_entity_detail failed: %s", e)
            return None

    async def get_neighborhood(
        self, entity_value: str, depth: int = 2, mask_pii: bool = True
    ) -> Dict[str, Any]:
        """Get entity node + 2-hop neighborhood with edges, capped at 200 nodes."""
        await self._ensure_connected()
        if not self.connected or not self.driver:
            return {"nodes": [], "edges": []}

        from app.utils.pii import mask_phone, mask_vpa, mask_email, PHONE_PATTERN, VPA_PATTERN, EMAIL_PATTERN

        def _mask_label(value: str, etype: str) -> str:
            if not mask_pii:
                return value
            if etype == "PHONE" or PHONE_PATTERN.fullmatch(re.sub(r"\D", "", value)):
                return mask_phone(value)
            if VPA_PATTERN.fullmatch(value):
                return mask_vpa(value)
            if EMAIL_PATTERN.fullmatch(value):
                return mask_email(value)
            return value[:4] + "***" if len(value) > 4 else "***"

        query = """
        MATCH (n:Entity {value: $value})
        OPTIONAL MATCH (n)-[r:APPEARED_WITH]-(m:Entity)
        WHERE n <> m
        WITH n, collect(DISTINCT {src: n.value, dst: m.value, weight: r.weight, session_id: r.session_id}) AS edge_data,
             collect(DISTINCT m) AS neighbor_nodes
        UNWIND neighbor_nodes AS nn
        OPTIONAL MATCH (nn)-[r2:APPEARED_WITH]-(m2:Entity)
        WHERE nn <> m2 AND m2 <> n
        WITH n, edge_data,
             collect(DISTINCT nn) AS depth1_nodes,
             collect(DISTINCT {src: nn.value, dst: m2.value, weight: r2.weight, session_id: r2.session_id}) AS depth2_edges,
             collect(DISTINCT m2) AS depth2_nodes
        RETURN n.value AS center_value, n.entity_type AS center_type,
               n.graph_risk_score AS center_risk, n.pagerank_score AS center_pagerank,
               n.ring_id AS center_ring_id, n.report_count AS center_report_count,
               [x IN depth1_nodes | {value: x.value, entity_type: x.entity_type,
                 risk_score: x.graph_risk_score, pagerank: x.pagerank_score,
                 ring_id: x.ring_id, report_count: x.report_count}] AS depth1,
               [x IN depth2_nodes | {value: x.value, entity_type: x.entity_type,
                 risk_score: x.graph_risk_score, pagerank: x.pagerank_score,
                 ring_id: x.ring_id, report_count: x.report_count}] AS depth2,
               edge_data + depth2_edges AS all_edges
        """
        try:
            async with self.driver.session() as session:
                result = await session.run(query, value=entity_value)
                record = await result.single()
                if not record:
                    return {"nodes": [], "edges": []}

                nodes = []
                seen = set()

                center_id = _hash_value(entity_value) if mask_pii else entity_value
                center_node = {
                    "id": center_id,
                    "label": _mask_label(entity_value, record["center_type"] or ""),
                    "risk": record["center_risk"] or 0.0,
                    "entity_type": record["center_type"] or "UNKNOWN",
                    "ring_id": record["center_ring_id"],
                    "report_count": record["center_report_count"] or 0,
                    "propagated_risk": 0.0,
                }
                nodes.append(center_node)
                seen.add(center_id)

                for n in record.get("depth1", []):
                    nid = _hash_value(n["value"]) if mask_pii else n["value"]
                    if nid in seen:
                        continue
                    seen.add(nid)
                    nodes.append({
                        "id": nid,
                        "label": _mask_label(n["value"], n["entity_type"] or ""),
                        "risk": n.get("risk_score") or 0.0,
                        "entity_type": n.get("entity_type", "UNKNOWN"),
                        "ring_id": n.get("ring_id"),
                        "report_count": n.get("report_count") or 0,
                        "propagated_risk": 0.0,
                    })

                for n in record.get("depth2", []):
                    nid = _hash_value(n["value"]) if mask_pii else n["value"]
                    if nid in seen:
                        continue
                    seen.add(nid)
                    nodes.append({
                        "id": nid,
                        "label": _mask_label(n["value"], n["entity_type"] or ""),
                        "risk": n.get("risk_score") or 0.0,
                        "entity_type": n.get("entity_type", "UNKNOWN"),
                        "ring_id": n.get("ring_id"),
                        "report_count": n.get("report_count") or 0,
                        "propagated_risk": 0.0,
                    })

                edges = []
                seen_edges = set()
                for e in record.get("all_edges", []):
                    if not e.get("src") or not e.get("dst"):
                        continue
                    src_id = _hash_value(e["src"]) if mask_pii else e["src"]
                    dst_id = _hash_value(e["dst"]) if mask_pii else e["dst"]
                    key = tuple(sorted([src_id, dst_id]))
                    if key in seen_edges:
                        continue
                    seen_edges.add(key)
                    edges.append({
                        "source": src_id,
                        "target": dst_id,
                        "label": "APPEARED_WITH",
                        "weight": e.get("weight") or 1,
                    })

                return {"nodes": nodes[:200], "edges": edges[:400]}
        except Exception as e:
            logger.error("Neo4j get_neighborhood failed: %s", e)
            return {"nodes": [], "edges": []}

    async def get_shortest_path(
        self, from_value: str, to_value: str
    ) -> Optional[Dict[str, Any]]:
        """Find shortest path between two entities via Neo4j shortestPath."""
        await self._ensure_connected()
        if not self.connected or not self.driver:
            return None
        query = """
        MATCH (a:Entity {value: $from_val}), (b:Entity {value: $to_val})
        MATCH p = shortestPath((a)-[*..10]-(b))
        RETURN [n IN nodes(p) | {
            value: n.value, entity_type: n.entity_type,
            risk_score: n.graph_risk_score, ring_id: n.ring_id
        }] AS path_nodes,
        [r IN relationships(p) | {
            src: startNode(r).value, dst: endNode(r).value,
            label: type(r), weight: r.weight
        }] AS path_edges
        """
        try:
            async with self.driver.session() as session:
                result = await session.run(
                    query, from_val=from_value, to_val=to_value
                )
                record = await result.single()
                if not record:
                    return None
                return {
                    "nodes": record["path_nodes"],
                    "edges": record["path_edges"],
                }
        except Exception as e:
            logger.error("Neo4j get_shortest_path failed: %s", e)
            return None

    async def close(self) -> None:
        if self.driver:
            await self.driver.close()
        if self.redis:
            await self.redis.close()
