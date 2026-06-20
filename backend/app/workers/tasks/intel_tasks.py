"""Intelligence tasks for fraud ring detection.

Provides Celery tasks wrapping ring_detection logic for scheduled
and on-demand execution.
"""

import asyncio
import logging
from typing import Any, Dict

from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="app.workers.tasks.intel_tasks.detect_fraud_rings_task")
def detect_fraud_rings_task() -> Dict[str, Any]:
    """Celery task wrapping ring_detection.detect_fraud_rings()."""
    from app.services.graph.ring_detection import _detect_rings
    return asyncio.run(_detect_rings())


@celery_app.task(name="app.workers.tasks.intel_tasks.trigger_ring_check")
def trigger_ring_check(entity_value: str) -> Dict[str, Any]:
    """Bounded 2-hop check around a specific entity (on-ingest trigger)."""
    return asyncio.run(_trigger_ring_check_async(entity_value))


async def _trigger_ring_check_async(entity_value: str) -> Dict[str, Any]:
    """Async implementation of bounded 2-hop entity ring check."""
    from app.services.graph.entity_graph import FraudEntityGraph

    graph = FraudEntityGraph()
    try:
        if not graph.connected:
            return {"status": "skipped", "reason": "Neo4j not connected"}

        neighbors = await graph.get_neighbors(entity_value, depth=2)
        if len(neighbors) < 4:
            return {"status": "no_ring_suspected", "neighbors": len(neighbors)}

        await graph._ensure_connected()
        return {
            "status": "check_triggered",
            "entity": entity_value,
            "neighbor_count": len(neighbors),
        }
    finally:
        await graph.close()
