"""Graph visualization and fraud ring endpoints."""

import asyncio
import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_async_db
from app.auth import get_current_user, require_role
from app.models.user import User as UserModel
from app.models.ring import FraudRing

logger = logging.getLogger(__name__)
router = APIRouter()


# ---------------------------------------------------------------------------
# Existing schemas (kept for backward compat)
# ---------------------------------------------------------------------------

class GraphNode(BaseModel):
    data: dict


class GraphEdge(BaseModel):
    data: dict


class GraphVisualization(BaseModel):
    nodes: List[GraphNode]
    edges: List[GraphEdge]


class FraudRingResponse(BaseModel):
    ring_id: str
    entity_count: int
    total_reports: int
    top_scam_type: Optional[str]
    risk_level: str
    status: str
    detected_at: str


class RingDetailResponse(BaseModel):
    ring_id: str
    entity_count: int
    total_reports: int
    top_scam_type: Optional[str]
    risk_level: str
    status: str
    members: List[dict]
    detected_at: str


# ---------------------------------------------------------------------------
# New investigation schemas
# ---------------------------------------------------------------------------

class EntityNode(BaseModel):
    id: str
    label: str
    risk: float
    entity_type: str
    ring_id: Optional[str] = None
    report_count: int = 0
    propagated_risk: float = 0.0


class EntityEdge(BaseModel):
    source: str
    target: str
    label: str
    weight: int = 1


class RingMembership(BaseModel):
    ring_id: str
    risk_level: str
    entity_count: int
    status: str


class EntityNeighborhoodResponse(BaseModel):
    center: EntityNode
    nodes: List[EntityNode]
    edges: List[EntityEdge]
    ring_memberships: List[RingMembership]
    direct_risk: float
    propagated_risk: float


class PathNode(BaseModel):
    id: str
    label: str
    entity_type: str
    risk: float
    ring_id: Optional[str] = None


class PathEdge(BaseModel):
    source: str
    target: str
    label: str
    weight: int = 1


class PathResponse(BaseModel):
    found: bool
    path_length: int
    nodes: List[PathNode]
    edges: List[PathEdge]


class RingsPaginatedResponse(BaseModel):
    rings: List[FraudRingResponse]
    total: int
    page: int
    page_size: int


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _get_ring_memberships(ring_id: Optional[str]) -> List[RingMembership]:
    """Fetch ring membership details for a given ring_id."""
    if not ring_id:
        return []
    return [RingMembership(
        ring_id=ring_id,
        risk_level="",
        entity_count=0,
        status="",
    )]


# ---------------------------------------------------------------------------
# Existing endpoints
# ---------------------------------------------------------------------------

@router.get("/graph/visualize", response_model=GraphVisualization)
async def visualize_entity_graph(
    entity: str = Query(..., description="Entity value to center on"),
    depth: int = Query(default=2, ge=1, le=3),
    mask_entities: bool = Query(default=True, description="Mask PII in response"),
    current_user: UserModel = Depends(get_current_user),
):
    """Return Cytoscape-compatible graph JSON for entity and its neighbors."""
    from app.services.graph.entity_graph import FraudEntityGraph

    graph = FraudEntityGraph()
    try:
        result = await asyncio.wait_for(
            graph.get_graph_for_visualization(
                entity_value=entity,
                depth=depth,
                mask_pii=mask_entities,
            ),
            timeout=5.0,
        )
        return GraphVisualization(
            nodes=[GraphNode(data=n["data"]) for n in result["nodes"]],
            edges=[GraphEdge(data=e["data"]) for e in result["edges"]],
        )
    except asyncio.TimeoutError:
        logger.warning("Graph visualization timeout for entity: %s", entity)
        return GraphVisualization(nodes=[], edges=[])
    except Exception as e:
        logger.error("Graph visualization error: %s", e)
        return GraphVisualization(nodes=[], edges=[])
    finally:
        await graph.close()


@router.get(
    "/graph/rings",
    response_model=RingsPaginatedResponse,
)
async def list_fraud_rings(
    risk_level: Optional[str] = Query(default=None),
    status: Optional[str] = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_async_db),
):
    """List detected fraud rings with pagination and stats."""
    base = select(FraudRing)
    if risk_level:
        base = base.filter(FraudRing.risk_level == risk_level)
    if status:
        base = base.filter(FraudRing.status == status)

    count_q = select(func.count()).select_from(base.subquery())
    total = (await db.execute(count_q)).scalar() or 0

    query = base.order_by(FraudRing.detected_at.desc()).offset(
        (page - 1) * page_size
    ).limit(page_size)

    result = await db.execute(query)
    rings = result.scalars().all()
    return RingsPaginatedResponse(
        rings=[
            FraudRingResponse(
                ring_id=r.ring_id,
                entity_count=r.entity_count,
                total_reports=r.total_reports,
                top_scam_type=r.top_scam_type,
                risk_level=r.risk_level,
                status=r.status,
                detected_at=r.detected_at.isoformat() if r.detected_at else "",
            )
            for r in rings
        ],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/graph/rings/{ring_id}", response_model=RingDetailResponse)
async def get_ring_detail(
    ring_id: str,
    db: AsyncSession = Depends(get_async_db),
):
    """Get detailed info about a specific fraud ring including member entities."""
    result = await db.execute(select(FraudRing).filter(FraudRing.ring_id == ring_id))
    ring = result.scalars().first()
    if not ring:
        raise HTTPException(status_code=404, detail="Ring not found")

    from app.services.graph.entity_graph import FraudEntityGraph

    graph = FraudEntityGraph()
    try:
        members = await graph.get_neighbors(ring_id, depth=1) if graph.connected else []
    finally:
        await graph.close()

    return RingDetailResponse(
        ring_id=ring.ring_id,
        entity_count=ring.entity_count,
        total_reports=ring.total_reports,
        top_scam_type=ring.top_scam_type,
        risk_level=ring.risk_level,
        status=ring.status,
        members=members,
        detected_at=ring.detected_at.isoformat() if ring.detected_at else "",
    )


# ---------------------------------------------------------------------------
# New investigation endpoints
# ---------------------------------------------------------------------------

@router.get(
    "/graph/entity/{entity_type}/{entity_value}",
    response_model=EntityNeighborhoodResponse,
)
async def get_entity_neighborhood(
    entity_type: str,
    entity_value: str,
    depth: int = Query(default=2, ge=1, le=3),
    current_user: UserModel = Depends(require_role("analyst", "super_admin", "org_admin")),
    db: AsyncSession = Depends(get_async_db),
):
    """Return entity node + 2-hop neighborhood with ring membership and risk scores.

    PII is masked by default; full values visible only to super_admin.
    """
    from app.services.graph.entity_graph import FraudEntityGraph, _hash_value

    show_pii = current_user.role == "super_admin"
    graph = FraudEntityGraph()
    try:
        result = await asyncio.wait_for(
            graph.get_neighborhood(
                entity_value=entity_value,
                depth=depth,
                mask_pii=not show_pii,
            ),
            timeout=5.0,
        )

        center_id = _hash_value(entity_value) if not show_pii else entity_value
        direct_risk = await graph.get_entity_risk(entity_value)

        nodes = []
        center_node = None
        for n in result.get("nodes", []):
            node = EntityNode(
                id=n["id"],
                label=n["label"] if not show_pii else entity_value,
                risk=n.get("risk", 0.0),
                entity_type=n.get("entity_type", "UNKNOWN"),
                ring_id=n.get("ring_id"),
                report_count=n.get("report_count", 0),
                propagated_risk=n.get("propagated_risk", 0.0),
            )
            nodes.append(node)
            if n["id"] == center_id:
                center_node = node

        if center_node is None and nodes:
            center_node = nodes[0]

        edges = [
            EntityEdge(
                source=e["source"],
                target=e["target"],
                label=e.get("label", "APPEARED_WITH"),
                weight=e.get("weight", 1),
            )
            for e in result.get("edges", [])
        ]

        # Ring membership from Neo4j ring_id + DB lookup
        ring_memberships: List[RingMembership] = []
        if center_node and center_node.ring_id:
            db_result = await db.execute(
                select(FraudRing).filter(FraudRing.ring_id == center_node.ring_id)
            )
            ring = db_result.scalars().first()
            if ring:
                ring_memberships.append(RingMembership(
                    ring_id=ring.ring_id,
                    risk_level=ring.risk_level,
                    entity_count=ring.entity_count,
                    status=ring.status,
                ))

        propagated_risk = await graph.get_entity_risk(entity_value)

        return EntityNeighborhoodResponse(
            center=center_node or EntityNode(
                id=center_id, label=entity_value, risk=direct_risk,
                entity_type=entity_type,
            ),
            nodes=nodes,
            edges=edges,
            ring_memberships=ring_memberships,
            direct_risk=direct_risk,
            propagated_risk=propagated_risk,
        )
    except asyncio.TimeoutError:
        logger.warning("Entity neighborhood timeout: %s", entity_value)
        raise HTTPException(status_code=504, detail="Graph query timed out")
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Entity neighborhood error: %s", e)
        raise HTTPException(status_code=500, detail="Failed to fetch entity neighborhood")
    finally:
        await graph.close()


@router.get(
    "/graph/path",
    response_model=PathResponse,
)
async def get_shortest_path(
    from_type: str = Query(..., description="Source entity type"),
    from_value: str = Query(..., description="Source entity value"),
    to_type: str = Query(..., description="Target entity type"),
    to_value: str = Query(..., description="Target entity value"),
    current_user: UserModel = Depends(require_role("analyst", "super_admin", "org_admin")),
):
    """Find shortest path between two entities in the fraud graph.

    PII is masked by default; full values visible only to super_admin.
    """
    from app.services.graph.entity_graph import FraudEntityGraph, _hash_value

    show_pii = current_user.role == "super_admin"
    graph = FraudEntityGraph()
    try:
        raw = await asyncio.wait_for(
            graph.get_shortest_path(from_value=from_value, to_value=to_value),
            timeout=5.0,
        )

        if raw is None:
            return PathResponse(found=False, path_length=0, nodes=[], edges=[])

        nodes = []
        for n in raw.get("nodes", []):
            nid = n["value"] if show_pii else _hash_value(n["value"])
            label = n["value"] if show_pii else n["value"][:4] + "***"
            nodes.append(PathNode(
                id=nid,
                label=label,
                entity_type=n.get("entity_type", "UNKNOWN"),
                risk=n.get("risk_score", 0.0),
                ring_id=n.get("ring_id"),
            ))

        edges = []
        for e in raw.get("edges", []):
            src_id = e["src"] if show_pii else _hash_value(e["src"])
            dst_id = e["dst"] if show_pii else _hash_value(e["dst"])
            edges.append(PathEdge(
                source=src_id,
                target=dst_id,
                label=e.get("label", "APPEARED_WITH"),
                weight=e.get("weight", 1),
            ))

        return PathResponse(
            found=True,
            path_length=len(nodes),
            nodes=nodes,
            edges=edges,
        )
    except asyncio.TimeoutError:
        logger.warning("Shortest path timeout: %s -> %s", from_value, to_value)
        raise HTTPException(status_code=504, detail="Path query timed out")
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Shortest path error: %s", e)
        raise HTTPException(status_code=500, detail="Failed to find shortest path")
    finally:
        await graph.close()
