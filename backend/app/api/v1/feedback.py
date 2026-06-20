"""Feedback endpoint for analyst labeling."""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_async_db
from app.models.feedback import FeedbackLabel

logger = logging.getLogger(__name__)
router = APIRouter()


class FeedbackRequest(BaseModel):
    session_id: str = Field(..., min_length=1, max_length=100)
    original_risk_score: int = Field(..., ge=0, le=100)
    original_risk_level: str
    original_action: str
    analyst_label: str = Field(..., pattern="^(true_positive|false_positive|false_negative)$")
    notes: Optional[str] = Field(None, max_length=2000)
    analyst_email: Optional[str] = None


class FeedbackResponse(BaseModel):
    id: int
    message: str


@router.post("/feedback", response_model=FeedbackResponse, status_code=201)
async def submit_feedback(request: FeedbackRequest, db: AsyncSession = Depends(get_async_db)):
    """Submit analyst feedback on a fraud prediction."""
    try:
        label = FeedbackLabel(
            session_id=request.session_id,
            original_risk_score=request.original_risk_score,
            original_risk_level=request.original_risk_level,
            original_action=request.original_action,
            analyst_label=request.analyst_label,
            notes=request.notes,
            analyst_email=request.analyst_email,
        )
        db.add(label)
        await db.commit()
        await db.refresh(label)

        logger.info("Feedback submitted: session=%s label=%s", request.session_id, request.analyst_label)
        return FeedbackResponse(id=label.id, message="Feedback recorded. Thank you.")
    except Exception as e:
        logger.error("Error submitting feedback: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to submit feedback")


@router.get("/feedback/stats")
async def feedback_stats(db: AsyncSession = Depends(get_async_db)):
    """Get aggregate feedback statistics for model quality monitoring."""
    total = (await db.execute(select(func.count(FeedbackLabel.id)))).scalar() or 0
    tp = (await db.execute(select(func.count(FeedbackLabel.id)).filter(FeedbackLabel.analyst_label == "true_positive"))).scalar() or 0
    fp = (await db.execute(select(func.count(FeedbackLabel.id)).filter(FeedbackLabel.analyst_label == "false_positive"))).scalar() or 0
    fn = (await db.execute(select(func.count(FeedbackLabel.id)).filter(FeedbackLabel.analyst_label == "false_negative"))).scalar() or 0

    fpr = round(fp / total * 100, 2) if total > 0 else 0.0

    return {
        "total_feedback": total,
        "true_positives": tp,
        "false_positives": fp,
        "false_negatives": fn,
        "false_positive_rate": fpr,
    }
