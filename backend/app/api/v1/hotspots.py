"""Hotspot mapping endpoint with real geo aggregation."""

import logging
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_async_db
from app.models.entity import FlaggedEntity

logger = logging.getLogger(__name__)

router = APIRouter()


class HotspotPoint(BaseModel):
    region: str
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    fraud_count: int
    top_scam_type: str
    risk_level: str


class HotspotResponse(BaseModel):
    data_source: str
    total_regions: int
    hotspots: List[HotspotPoint]


def _risk_level(count: int) -> str:
    if count >= 100:
        return "critical"
    elif count >= 50:
        return "high"
    elif count >= 20:
        return "medium"
    return "low"


@router.get(
    "/analytics/hotspots",
    response_model=HotspotResponse,
    responses={500: {"model": dict}},
)
async def get_fraud_hotspots(
    days: int = Query(default=30, ge=1, le=90),
    db: AsyncSession = Depends(get_async_db),
) -> HotspotResponse:
    """Get real fraud hotspot data from flagged_entities with geo columns."""
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)

        result = await db.execute(
            select(
                FlaggedEntity.region,
                func.count(FlaggedEntity.id).label("count"),
                func.max(FlaggedEntity.scam_type).label("top_type"),
                func.avg(FlaggedEntity.latitude).label("avg_lat"),
                func.avg(FlaggedEntity.longitude).label("avg_lng"),
            )
            .filter(
                FlaggedEntity.region.isnot(None),
                FlaggedEntity.last_seen >= cutoff,
            )
            .group_by(FlaggedEntity.region)
            .order_by(func.count(FlaggedEntity.id).desc())
        )
        rows = result.all()

        if not rows:
            return HotspotResponse(
                data_source="empty",
                total_regions=0,
                hotspots=[],
            )

        hotspots = []
        for row in rows:
            hotspots.append(HotspotPoint(
                region=row.region,
                latitude=round(row.avg_lat, 4) if row.avg_lat else None,
                longitude=round(row.avg_lng, 4) if row.avg_lng else None,
                fraud_count=row.count,
                top_scam_type=row.top_type or "unknown",
                risk_level=_risk_level(row.count),
            ))

        return HotspotResponse(
            data_source="flagged_entities",
            total_regions=len(hotspots),
            hotspots=hotspots,
        )

    except Exception as e:
        logger.error("Error fetching hotspot data: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch hotspot data")
