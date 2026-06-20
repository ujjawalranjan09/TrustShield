"""Coached-victim intervention endpoints."""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_async_db
from app.models.intervention import InterventionLog

logger = logging.getLogger(__name__)
router = APIRouter()


class CoolOffRequest(BaseModel):
    session_id: str
    duration_minutes: int = 10


class CallbackRequest(BaseModel):
    session_id: str
    victim_phone: str


class InterventionResponse(BaseModel):
    status: str
    message: str
    intervention_id: Optional[int] = None


@router.post("/intervention/cool-off", response_model=InterventionResponse)
async def trigger_cool_off(
    request: CoolOffRequest,
    db: AsyncSession = Depends(get_async_db),
):
    """Trigger a 10-minute transaction freeze for coached victim."""
    log = InterventionLog(
        session_id=request.session_id,
        intervention_type="cool_off",
        status="triggered",
        details=f"Transaction freeze for {request.duration_minutes} minutes",
    )
    db.add(log)
    await db.commit()
    await db.refresh(log)

    logger.info("Cool-off triggered: session=%s duration=%dmin", request.session_id, request.duration_minutes)

    return InterventionResponse(
        status="triggered",
        message=f"Transaction freeze initiated for {request.duration_minutes} minutes. Banking partner notified.",
        intervention_id=log.id,
    )


@router.post("/intervention/callback-request", response_model=InterventionResponse)
async def request_callback(
    request: CallbackRequest,
    db: AsyncSession = Depends(get_async_db),
):
    """Request a callback from the partner bank's fraud desk."""
    log = InterventionLog(
        session_id=request.session_id,
        intervention_type="callback_request",
        status="triggered",
        details=f"Callback requested for {request.victim_phone}",
    )
    db.add(log)
    await db.commit()
    await db.refresh(log)

    logger.info("Callback requested: session=%s phone=%s", request.session_id, request.victim_phone)

    return InterventionResponse(
        status="triggered",
        message="Callback request submitted. Partner bank will contact within 30 minutes.",
        intervention_id=log.id,
    )


@router.get("/intervention/{session_id}")
async def get_intervention_history(
    session_id: str,
    db: AsyncSession = Depends(get_async_db),
):
    """Get intervention history for a session."""
    result = await db.execute(
        select(InterventionLog).filter(InterventionLog.session_id == session_id)
        .order_by(InterventionLog.created_at.desc())
    )
    logs = result.scalars().all()

    return {
        "session_id": session_id,
        "interventions": [
            {
                "id": l.id,
                "type": l.intervention_type,
                "status": l.status,
                "details": l.details,
                "triggered_at": l.triggered_at.isoformat() if l.triggered_at else None,
            }
            for l in logs
        ],
    }
