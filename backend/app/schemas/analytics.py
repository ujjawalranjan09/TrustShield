"""Analytics dashboard schemas."""

from datetime import datetime
from typing import Any, Dict, List

from pydantic import BaseModel


class RiskDistribution(BaseModel):
    low: int
    medium: int
    high: int
    critical: int
    total: int


class ScamTypeBreakdown(BaseModel):
    scam_type: str
    count: int
    percentage: float


class ContributingFactor(BaseModel):
    factor: str
    weight: float
    description: str


class TemporalPoint(BaseModel):
    date: str
    reports: int
    confirmed: int


class DashboardStats(BaseModel):
    total_sessions: int
    flagged_sessions: int
    avg_risk_score: float
    top_scam_types: List[str]


class DashboardStatsFull(BaseModel):
    total_scans_today: int
    flagged_sessions: int
    entities_blacklisted: int
    false_positive_rate: float
    risk_distribution: RiskDistribution
    scam_type_breakdown: List[ScamTypeBreakdown]
    top_entities: List[Dict[str, Any]]
    contributing_factors: List[ContributingFactor]
    temporal_trend: List[TemporalPoint]


class TimeSeriesPoint(BaseModel):
    timestamp: datetime
    value: float
