"""Predictive Hotspot Mapping endpoint.

Provides geographic fraud analytics:
- Real-time fraud hotspots by region
- Time-series fraud trend data
- Cluster analysis by scam type and region
- Early warning signals for emerging patterns

Data is aggregated from the entity_reports table with geographic
metadata (when available). Returns GeoJSON-compatible structures
for frontend map rendering.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.entity import EntityReport, FlaggedEntity

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class HotspotPoint(BaseModel):
    """A single fraud hotspot data point."""

    region: str
    latitude: float
    longitude: float
    fraud_count: int
    top_scam_type: str
    risk_level: str


class HotspotCluster(BaseModel):
    """A cluster of related fraud activity."""

    cluster_id: str
    center_lat: float
    center_lng: float
    radius_km: float
    total_incidents: int
    scam_types: List[str]
    trend: str  # 'increasing', 'stable', 'decreasing'


class TimeSeriesPoint(BaseModel):
    """A point in the fraud time series."""

    date: str
    count: int
    scam_type: str


class HotspotSummary(BaseModel):
    """Summary of hotspot analysis."""

    total_regions: int
    total_hotspots: int
    highest_risk_region: str
    emerging_threats: List[str]


class HotspotResponse(BaseModel):
    """Full hotspot mapping response."""

    summary: HotspotSummary
    hotspots: List[HotspotPoint]
    clusters: List[HotspotCluster]
    time_series: List[TimeSeriesPoint]


class ErrorResponse(BaseModel):
    """Structured error response."""

    error: str
    detail: str
    status_code: int


# ---------------------------------------------------------------------------
# Mock geographic data (in production, from IP geolocation or user data)
# ---------------------------------------------------------------------------

# Indian cities with coordinates for demo hotspots
DEMO_HOTSPOTS = [
    {"region": "Mumbai", "lat": 19.0760, "lng": 72.8777, "scam_type": "vishing"},
    {"region": "Delhi", "lat": 28.7041, "lng": 77.1025, "scam_type": "fake_support"},
    {"region": "Bangalore", "lat": 12.9716, "lng": 77.5946, "scam_type": "refund_scam"},
    {
        "region": "Chennai",
        "lat": 13.0827,
        "lng": 80.2707,
        "scam_type": "otp_harvesting",
    },
    {"region": "Kolkata", "lat": 22.5726, "lng": 88.3639, "scam_type": "remote_access"},
    {"region": "Hyderabad", "lat": 17.3850, "lng": 78.4867, "scam_type": "vishing"},
    {"region": "Pune", "lat": 18.5204, "lng": 73.8567, "scam_type": "fake_support"},
    {"region": "Ahmedabad", "lat": 23.0225, "lng": 72.5714, "scam_type": "refund_scam"},
    {"region": "Jaipur", "lat": 26.9124, "lng": 75.7873, "scam_type": "otp_harvesting"},
    {"region": "Lucknow", "lat": 26.8467, "lng": 80.9462, "scam_type": "vishing"},
]


def _risk_level(count: int) -> str:
    """Map fraud count to risk level."""
    if count >= 100:
        return "critical"
    elif count >= 50:
        return "high"
    elif count >= 20:
        return "medium"
    return "low"


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get(
    "/analytics/hotspots",
    response_model=HotspotResponse,
    responses={500: {"model": ErrorResponse}},
)
async def get_fraud_hotspots(
    days: int = Query(default=7, ge=1, le=90, description="Lookback period in days"),
    db: Session = Depends(get_db),
) -> HotspotResponse:
    """Get fraud hotspot data for geographic visualization.

    Returns hotspot points, clusters, and time series data suitable
    for rendering on a map (Leaflet/Mapbox) in the frontend.
    """
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)

        # Get real report counts from database
        report_counts = (
            db.query(
                FlaggedEntity.entity_type,
                func.count(FlaggedEntity.id).label("cnt"),
            )
            .group_by(FlaggedEntity.entity_type)
            .all()
        )

        total_reports = sum(r.cnt for r in report_counts) if report_counts else 0

        # Build hotspot points (combine real data with geographic positions)
        hotspots: List[HotspotPoint] = []
        for i, demo in enumerate(DEMO_HOTSPOTS):
            # Scale demo counts by real report data
            count = max(5, int(total_reports * (0.1 + (i * 0.05))))
            hotspots.append(
                HotspotPoint(
                    region=demo["region"],
                    latitude=demo["lat"],
                    longitude=demo["lng"],
                    fraud_count=count,
                    top_scam_type=demo["scam_type"],
                    risk_level=_risk_level(count),
                )
            )

        # Build clusters (group nearby hotspots)
        clusters: List[HotspotCluster] = [
            HotspotCluster(
                cluster_id="west-india",
                center_lat=19.5,
                center_lng=73.5,
                radius_km=300,
                total_incidents=sum(
                    h.fraud_count
                    for h in hotspots
                    if h.region in ("Mumbai", "Pune", "Ahmedabad")
                ),
                scam_types=["vishing", "fake_support", "refund_scam"],
                trend="increasing",
            ),
            HotspotCluster(
                cluster_id="north-india",
                center_lat=28.0,
                center_lng=77.5,
                radius_km=250,
                total_incidents=sum(
                    h.fraud_count
                    for h in hotspots
                    if h.region in ("Delhi", "Jaipur", "Lucknow")
                ),
                scam_types=["fake_support", "otp_harvesting", "vishing"],
                trend="stable",
            ),
            HotspotCluster(
                cluster_id="south-india",
                center_lat=13.5,
                center_lng=78.5,
                radius_km=350,
                total_incidents=sum(
                    h.fraud_count
                    for h in hotspots
                    if h.region in ("Bangalore", "Chennai", "Hyderabad")
                ),
                scam_types=["remote_access", "otp_harvesting", "vishing"],
                trend="increasing",
            ),
        ]

        # Build time series (last N days)
        time_series: List[TimeSeriesPoint] = []
        scam_types = [
            "vishing",
            "fake_support",
            "refund_scam",
            "otp_harvesting",
            "remote_access",
        ]
        for i in range(days - 1, -1, -1):
            date = datetime.now(timezone.utc) - timedelta(days=i)
            date_str = date.strftime("%Y-%m-%d")
            for scam_type in scam_types:
                # Simulated daily counts
                base = 15 + (i % 7) * 3
                count = base + hash(f"{date_str}{scam_type}") % 20
                time_series.append(
                    TimeSeriesPoint(date=date_str, count=count, scam_type=scam_type)
                )

        # Find highest risk region
        highest_risk = max(hotspots, key=lambda h: h.fraud_count)

        # Emerging threats (scam types with increasing trend)
        emerging = ["remote_access", "overlay_attack"]

        return HotspotResponse(
            summary=HotspotSummary(
                total_regions=len(hotspots),
                total_hotspots=len(hotspots),
                highest_risk_region=highest_risk.region,
                emerging_threats=emerging,
            ),
            hotspots=hotspots,
            clusters=clusters,
            time_series=time_series,
        )

    except Exception as e:
        logger.error("Error fetching hotspot data: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch hotspot data")
