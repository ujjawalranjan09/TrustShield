"""Entity graph module.

Provides a Neo4j-backed graph interface for storing and querying fraud
entity relationships. Uses the official neo4j Python driver with async
support. Falls back gracefully if Neo4j is unavailable.
"""

import logging
from typing import Any, Dict, List, Optional

from pydantic import BaseModel

from app.config import NEO4J_URI, NEO4J_PASSWORD, NEO4J_USER

logger = logging.getLogger(__name__)

try:
    from neo4j import AsyncGraphDatabase

    _neo4j_available = True
except ImportError:
    _neo4j_available = False
    logger.warning("neo4j package not installed — graph features disabled")


class FlaggedEntity(BaseModel):
    """An entity flagged for suspicious activity."""

    value: str
    entity_type: str
    report_count: int = 0
    graph_risk_score: float = 0.0


class FraudEntityGraph:
    """Neo4j-backed graph for fraud entity relationships.

    Connects to Neo4j using the async driver. If the connection fails,
    operations gracefully degrade to no-ops with logged warnings.
    """

    def __init__(self) -> None:
        self.driver: Optional[Any] = None
        self.connected: bool = False
        self._connect()

    def _connect(self) -> None:
        """Initialize the Neo4j async driver."""
        if not _neo4j_available:
            return
        try:
            self.driver = AsyncGraphDatabase.driver(
                NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD)
            )
            self.connected = True
            logger.info("Connected to Neo4j at %s", NEO4J_URI)
        except Exception as e:
            logger.warning("Failed to connect to Neo4j: %s", e)
            self.connected = False

    async def add_entity(self, entity: FlaggedEntity) -> None:
        """Upsert an entity node into the graph.

        Args:
            entity: The flagged entity to add or update.
        """
        if not self.connected or not self.driver:
            logger.debug("Neo4j unavailable, skipping add_entity")
            return

        query = """
        MERGE (n:Entity {value: $value})
        ON CREATE SET n.entity_type = $type, n.report_count = $report_count,
                      n.first_seen = timestamp(), n.last_seen = timestamp(),
                      n.graph_risk_score = $graph_risk_score
        ON MATCH SET n.report_count = n.report_count + 1, n.last_seen = timestamp()
        """
        try:
            async with self.driver.session() as session:
                await session.run(
                    query,
                    value=entity.value,
                    type=entity.entity_type,
                    report_count=entity.report_count,
                    graph_risk_score=entity.graph_risk_score,
                )
            logger.debug("add_entity: %s (%s)", entity.value, entity.entity_type)
        except Exception as e:
            logger.error("Neo4j add_entity failed: %s", e)

    async def add_session_link(
        self, entity_a_id: str, entity_b_id: str, session_id: str
    ) -> None:
        """Create an APPEARED_WITH relationship between two entities.

        Args:
            entity_a_id: Value of the first entity node.
            entity_b_id: Value of the second entity node.
            session_id: Session in which both entities appeared.
        """
        if not self.connected or not self.driver:
            logger.debug("Neo4j unavailable, skipping add_session_link")
            return

        query = """
        MATCH (a:Entity {value: $a_val}), (b:Entity {value: $b_val})
        MERGE (a)-[r:APPEARED_WITH {session_id: $session_id}]-(b)
        ON CREATE SET r.timestamp = timestamp()
        """
        try:
            async with self.driver.session() as session:
                await session.run(
                    query,
                    a_val=entity_a_id,
                    b_val=entity_b_id,
                    session_id=session_id,
                )
            logger.debug(
                "add_session_link: %s <-> %s (session %s)",
                entity_a_id,
                entity_b_id,
                session_id,
            )
        except Exception as e:
            logger.error("Neo4j add_session_link failed: %s", e)

    async def get_entity_risk(self, entity_value: str) -> float:
        """Get the graph-based risk score for an entity.

        Args:
            entity_value: The entity value to look up.

        Returns:
            Risk score between 0.0 and 1.0.
        """
        if not self.connected or not self.driver:
            return 0.0

        query = """
        MATCH (n:Entity {value: $value})
        OPTIONAL MATCH (n)--(m)
        RETURN n.graph_risk_score AS base_score, count(m) AS degree
        """
        try:
            async with self.driver.session() as session:
                result = await session.run(query, value=entity_value)
                record = await result.single()
                if record:
                    base_score = record["base_score"] or 0.0
                    degree = record["degree"] or 0
                    # Boost risk based on connections to known bad actors
                    connection_boost = min(0.3, degree * 0.05)
                    return min(1.0, base_score + connection_boost)
            return 0.0
        except Exception as e:
            logger.error("Neo4j get_entity_risk failed: %s", e)
            return 0.0

    async def get_connected_entities(
        self, entity_value: str, depth: int = 2
    ) -> List[Dict[str, Any]]:
        """Get entities connected to the given entity within `depth` hops.

        Args:
            entity_value: The entity value to start from.
            depth: Maximum traversal depth.

        Returns:
            List of dicts with 'value' and 'type' keys.
        """
        if not self.connected or not self.driver:
            return []

        query = """
        MATCH (n:Entity {value: $value})-[*1..$depth]-(m)
        RETURN DISTINCT m.value AS value, m.entity_type AS type
        """
        try:
            async with self.driver.session() as session:
                result = await session.run(query, value=entity_value, depth=depth)
                return [dict(record) async for record in result]
        except Exception as e:
            logger.error("Neo4j get_connected_entities failed: %s", e)
            return []

    async def bulk_upsert(self, entities: List[FlaggedEntity]) -> None:
        """Bulk upsert multiple entity nodes.

        Args:
            entities: List of flagged entities to upsert.
        """
        if not self.connected or not self.driver:
            logger.debug("Neo4j unavailable, skipping bulk_upsert")
            return

        query = """
        UNWIND $entities AS entity
        MERGE (n:Entity {value: entity.value})
        ON CREATE SET n.entity_type = entity.type, n.first_seen = timestamp(),
                      n.report_count = 1
        ON MATCH SET n.report_count = n.report_count + 1, n.last_seen = timestamp()
        """
        try:
            async with self.driver.session() as session:
                await session.run(
                    query,
                    entities=[e.model_dump() for e in entities],
                )
            logger.debug("bulk_upsert: %d entities", len(entities))
        except Exception as e:
            logger.error("Neo4j bulk_upsert failed: %s", e)

    async def close(self) -> None:
        """Close the Neo4j driver connection."""
        if self.driver:
            await self.driver.close()
            logger.info("Neo4j connection closed")
