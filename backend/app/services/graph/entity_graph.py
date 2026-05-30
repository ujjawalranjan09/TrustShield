class FlaggedEntity:
    def __init__(self, value: str, entity_type: str, report_count: int = 0, graph_risk_score: float = 0.0):
        self.value = value
        self.entity_type = entity_type
        self.report_count = report_count
        self.graph_risk_score = graph_risk_score

class FraudEntityGraph:
    def __init__(self):
        # We would use Neo4j AsyncGraphDatabase.driver here.
        # e.g., self.driver = AsyncGraphDatabase.driver(uri, auth=(user, password))
        self.connected = True

    async def add_entity(self, entity: FlaggedEntity):
        query = """
        MERGE (n:Entity {value: $value})
        ON CREATE SET n.entity_type = $type, n.report_count = $report_count, n.first_seen = timestamp(), n.last_seen = timestamp(), n.graph_risk_score = $graph_risk_score
        ON MATCH SET n.report_count = n.report_count + 1, n.last_seen = timestamp()
        """
        # Mock execution: await session.run(query, value=entity.value, ...)
        pass

    async def add_session_link(self, entity_a_id: str, entity_b_id: str, session_id: str):
        query = """
        MATCH (a:Entity {value: $a_val}), (b:Entity {value: $b_val})
        MERGE (a)-[r:APPEARED_WITH {session_id: $session_id}]-(b)
        ON CREATE SET r.timestamp = timestamp()
        """
        # Mock execution
        pass

    async def get_entity_risk(self, entity_value: str) -> float:
        # Simplistic risk calculation: fetch node's graph_risk_score + neighbors
        query = """
        MATCH (n:Entity {value: $value})
        OPTIONAL MATCH (n)--(m)
        RETURN n.graph_risk_score AS base_score, count(m) AS degree
        """
        # Mock execution: return calculated score
        return 0.5

    async def get_connected_entities(self, entity_value: str, depth: int = 2) -> list:
        query = """
        MATCH (n:Entity {value: $value})-[*1..$depth]-(m)
        RETURN DISTINCT m.value AS value, m.entity_type AS type
        """
        # Mock execution
        return [{"value": "123456789", "type": "ANYDESK"}]

    async def bulk_upsert(self, entities: list[FlaggedEntity]):
        query = """
        UNWIND $entities AS entity
        MERGE (n:Entity {value: entity.value})
        ON CREATE SET n.entity_type = entity.type, n.first_seen = timestamp(), n.report_count = 1
        ON MATCH SET n.report_count = n.report_count + 1, n.last_seen = timestamp()
        """
        # Mock execution
        pass

    async def close(self):
        # Mock close: await self.driver.close()
        pass
