"""Analytics and explainability endpoints."""

import logging
from datetime import datetime, timezone
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_async_db
from app.models.entity import EntityReport, FlaggedEntity
from app.models.scan_event import ScanEvent
from app.schemas.analytics import (
    ContributingFactor,
    DashboardStatsFull,
    RiskDistribution,
    ScamTypeBreakdown,
    TemporalPoint,
)

logger = logging.getLogger(__name__)

router = APIRouter()

# Backward-compatible re-exports
RiskDistribution = RiskDistribution
ScamTypeBreakdown = ScamTypeBreakdown
ContributingFactor = ContributingFactor
TemporalPoint = TemporalPoint
DashboardStats = DashboardStatsFull
ErrorResponse = Dict[str, Any]  # legacy: analytics used a local ErrorResponse with status_code


DEFAULT_CONTRIBUTING_FACTORS = [
    ContributingFactor(
        factor="NLP Classifier Confidence",
        weight=0.35,
        description="Keyword and pattern matching confidence from the scam classifier",
    ),
    ContributingFactor(
        factor="High-Risk Entity Presence",
        weight=0.25,
        description="Detection of remote access tools (AnyDesk, TeamViewer), shortlinks, or APKs",
    ),
    ContributingFactor(
        factor="Contact Initiation Direction",
        weight=0.20,
        description="Whether the contact was initiated by an unknown sender",
    ),
    ContributingFactor(
        factor="Prior Fraud Reports",
        weight=0.20,
        description="Number of independent fraud reports against this entity",
    ),
]


@router.get(
    "/analytics/dashboard",
    response_model=DashboardStats,
    responses={500: {"model": ErrorResponse}},
)
async def get_dashboard_stats(db: AsyncSession = Depends(get_async_db)) -> DashboardStats:
    """Get comprehensive dashboard statistics."""
    try:
        total_entities = (await db.execute(select(func.count(FlaggedEntity.id)))).scalar() or 0
        total_reports = (await db.execute(select(func.coalesce(func.sum(FlaggedEntity.report_count), 0)))).scalar()

        low = (await db.execute(select(func.count(FlaggedEntity.id)).filter(FlaggedEntity.report_count < 3))).scalar() or 0
        medium = (await db.execute(select(func.count(FlaggedEntity.id)).filter(FlaggedEntity.report_count >= 3, FlaggedEntity.report_count < 5))).scalar() or 0
        high = (await db.execute(select(func.count(FlaggedEntity.id)).filter(FlaggedEntity.report_count >= 5, FlaggedEntity.report_count < 10))).scalar() or 0
        critical = (await db.execute(select(func.count(FlaggedEntity.id)).filter(FlaggedEntity.report_count >= 10))).scalar() or 0

        risk_dist = RiskDistribution(low=low, medium=medium, high=high, critical=critical, total=total_entities)

        scam_type_result = await db.execute(
            select(FlaggedEntity.scam_type, func.count(FlaggedEntity.id).label("cnt"))
            .filter(FlaggedEntity.scam_type.isnot(None))
            .group_by(FlaggedEntity.scam_type)
            .order_by(func.count(FlaggedEntity.id).desc())
            .limit(10)
        )
        scam_type_rows = scam_type_result.all()

        scam_breakdown = []
        for row in scam_type_rows:
            pct = (row.cnt / total_entities * 100) if total_entities > 0 else 0
            scam_breakdown.append(ScamTypeBreakdown(scam_type=row.scam_type, count=row.cnt, percentage=round(pct, 1)))

        top_result = await db.execute(
            select(FlaggedEntity).order_by(FlaggedEntity.report_count.desc()).limit(10)
        )
        top_entities_q = top_result.scalars().all()
        top_entities = [
            {
                "entity_value": e.entity_value,
                "entity_type": e.entity_type,
                "report_count": e.report_count,
                "scam_type": e.scam_type,
                "risk_level": (
                    "critical" if e.report_count >= 10
                    else "high" if e.report_count >= 5
                    else "medium" if e.report_count >= 3
                    else "low"
                ),
            }
            for e in top_entities_q
        ]

        now = datetime.now(timezone.utc)
        temporal_trend = []
        for i in range(6, -1, -1):
            day = now.replace(hour=0, minute=0, second=0, microsecond=0)
            day = day.replace(day=max(1, day.day - i))
            next_day = day.replace(day=day.day + 1) if day.day < 28 else day

            day_reports = (await db.execute(
                select(func.count(EntityReport.id)).filter(
                    EntityReport.created_at >= day, EntityReport.created_at < next_day
                )
            )).scalar() or 0

            day_confirmed = (await db.execute(
                select(func.count(FlaggedEntity.id)).filter(
                    FlaggedEntity.first_reported >= day,
                    FlaggedEntity.first_reported < next_day,
                    FlaggedEntity.is_confirmed == 1,
                )
            )).scalar() or 0

            temporal_trend.append(TemporalPoint(date=day.strftime("%Y-%m-%d"), reports=day_reports, confirmed=day_confirmed))

        today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        scans_today = (await db.execute(select(func.count(ScanEvent.id)).filter(ScanEvent.created_at >= today_start))).scalar() or 0

        return DashboardStats(
            total_scans_today=scans_today,
            flagged_sessions=total_reports,
            entities_blacklisted=total_entities,
            false_positive_rate=0.0,
            risk_distribution=risk_dist,
            scam_type_breakdown=scam_breakdown,
            top_entities=top_entities,
            contributing_factors=DEFAULT_CONTRIBUTING_FACTORS,
            temporal_trend=temporal_trend,
        )

    except Exception as e:
        logger.error("Error fetching dashboard stats: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to fetch dashboard stats: {str(e)}")


@router.get("/analytics/time-series")
async def get_time_series(
    days: int = 7,
    db: AsyncSession = Depends(get_async_db),
):
    """Get fraud time-series data for charting."""
    from datetime import timedelta
    now = datetime.now(timezone.utc)
    points = []
    for i in range(days - 1, -1, -1):
        day = now - timedelta(days=i)
        day_start = day.replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = day_start + timedelta(days=1)
        count = (await db.execute(
            select(func.count(EntityReport.id)).filter(
                EntityReport.created_at >= day_start,
                EntityReport.created_at < day_end,
            )
        )).scalar() or 0
        points.append({"date": day_start.strftime("%Y-%m-%d"), "count": count})
    return points
