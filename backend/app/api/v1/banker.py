"""Banker dashboard — bank-scoped analytics and sessions."""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import require_role
from app.database import get_async_db
from app.models.intervention import InterventionLog
from app.models.scan_event import ScanEvent
from app.models.feedback import FeedbackLabel
from app.models.user import User
from app.services.intervention.bank_channel import send_freeze_request

logger = logging.getLogger(__name__)
router = APIRouter()

# All banker endpoints require bank, org_admin, or super_admin role
_banker_auth = require_role("bank", "org_admin", "super_admin")


class BankerDashboardStats(BaseModel):
    total_sessions: int
    flagged_sessions: int
    false_positive_rate: float
    avg_risk_score: float
    top_scam_types: list


class BankerSession(BaseModel):
    session_id: str
    risk_score: int
    risk_level: str
    action_taken: str
    created_at: str


@router.get("/banker/dashboard", response_model=BankerDashboardStats)
async def banker_dashboard(
    current_user: User = Depends(_banker_auth),
    db: AsyncSession = Depends(get_async_db),
):
    """Bank-specific dashboard stats."""
    total = (await db.execute(select(func.count(ScanEvent.id)))).scalar() or 0
    flagged = (await db.execute(
        select(func.count(ScanEvent.id)).filter(ScanEvent.risk_level.in_(["high", "critical"]))
    )).scalar() or 0

    avg_result = (await db.execute(select(func.avg(ScanEvent.risk_score)))).scalar()
    avg_score = round(float(avg_result or 0), 1)

    total_feedback = (await db.execute(select(func.count(FeedbackLabel.id)))).scalar() or 0
    fp = (await db.execute(
        select(func.count(FeedbackLabel.id)).filter(FeedbackLabel.analyst_label == "false_positive")
    )).scalar() or 0
    fpr = round(fp / total_feedback * 100, 1) if total_feedback > 0 else 0.0

    scam_result = await db.execute(
        select(ScanEvent.risk_level, func.count(ScanEvent.id).label("cnt"))
        .group_by(ScanEvent.risk_level).order_by(func.count(ScanEvent.id).desc()).limit(5)
    )
    top_scam = [{"level": r.risk_level, "count": r.cnt} for r in scam_result.all()]

    return BankerDashboardStats(
        total_sessions=total,
        flagged_sessions=flagged,
        false_positive_rate=fpr,
        avg_risk_score=avg_score,
        top_scam_types=top_scam,
    )


@router.get("/banker/sessions", response_model=list)
async def banker_sessions(
    limit: int = Query(default=50, le=200),
    current_user: User = Depends(_banker_auth),
    db: AsyncSession = Depends(get_async_db),
):
    """Bank's flagged sessions."""
    result = await db.execute(
        select(ScanEvent).order_by(ScanEvent.created_at.desc()).limit(limit)
    )
    sessions = result.scalars().all()
    return [
        BankerSession(
            session_id=s.session_id,
            risk_score=s.risk_score,
            risk_level=s.risk_level,
            action_taken=s.action_taken or "",
            created_at=s.created_at.isoformat() if s.created_at else "",
        )
        for s in sessions
    ]


class FreezeRequest(BaseModel):
    case_id: str
    entity: str
    risk: float
    ttl_seconds: int = 3600


class FreezeResponse(BaseModel):
    status: str
    bank_id: str | None = None
    reason: str | None = None


@router.post("/banker/request-freeze", response_model=FreezeResponse)
async def request_freeze(
    body: FreezeRequest,
    current_user: User = Depends(_banker_auth),
    db: AsyncSession = Depends(get_async_db),
):
    """Request a bank freeze/hold on a victim's account."""
    result = await send_freeze_request(
        case_id=body.case_id,
        victim_entity=body.entity,
        risk=body.risk,
        recommended_action="hold",
        ttl_seconds=body.ttl_seconds,
        db=db,
    )
    return FreezeResponse(**result)


class InterventionEntry(BaseModel):
    id: int
    session_id: str
    intervention_type: str
    status: str
    details: str | None = None
    triggered_at: str | None = None


@router.get("/banker/interventions", response_model=list[InterventionEntry])
async def list_interventions(
    status_filter: Optional[str] = Query(default=None, alias="status"),
    limit: int = Query(default=50, le=200),
    current_user: User = Depends(_banker_auth),
    db: AsyncSession = Depends(get_async_db),
):
    """List InterventionLog entries, optionally filtered by status."""
    stmt = select(InterventionLog).order_by(InterventionLog.created_at.desc())
    if status_filter:
        stmt = stmt.filter(InterventionLog.status == status_filter)
    stmt = stmt.limit(limit)
    result = await db.execute(stmt)
    logs = result.scalars().all()
    return [
        InterventionEntry(
            id=log.id,
            session_id=log.session_id,
            intervention_type=log.intervention_type,
            status=log.status,
            details=log.details,
            triggered_at=log.triggered_at.isoformat() if log.triggered_at else None,
        )
        for log in logs
    ]
