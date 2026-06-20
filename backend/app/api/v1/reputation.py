"""Merchant/VPA Reputation API — public score + widget + enriched service."""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_async_db
from app.services.intel.reputation_service import compute_reputation, get_public_reputation

logger = logging.getLogger(__name__)
router = APIRouter()


class ReputationResponse(BaseModel):
    entity: str
    reputation_tier: str
    score: int
    direct_reports: int
    propagated_risk: float
    ring_membership: Optional[str] = None
    last_reported_at: Optional[str] = None
    first_seen: Optional[str] = None


class PublicReputationResponse(BaseModel):
    entity: str
    reputation_tier: str
    score: int
    report_count_bucket: str


@router.get("/reputation/{vpa:path}/widget")
async def get_reputation_widget(vpa: str, db: AsyncSession = Depends(get_async_db)):
    """Return SVG badge for VPA reputation."""
    rep = await compute_reputation(vpa, "UPI", db)

    if rep.get("reputation_tier") == "unknown" or rep.get("score", 0) == 0:
        color, text = "#6b7280", "Unknown"
    elif rep["score"] >= 80:
        color, text = "#22c55e", f"Score: {rep['score']}"
    elif rep["score"] >= 50:
        color, text = "#f97316", f"Score: {rep['score']}"
    else:
        color, text = "#ef4444", f"Score: {rep['score']}"

    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="120" height="28" viewBox="0 0 120 28">
  <rect width="120" height="28" rx="6" fill="{color}" opacity="0.15"/>
  <rect width="120" height="28" rx="6" fill="none" stroke="{color}" stroke-width="1.5"/>
  <text x="60" y="18" text-anchor="middle" font-family="Arial" font-size="12" font-weight="bold" fill="{color}">{text}</text>
</svg>'''

    return Response(content=svg, media_type="image/svg+xml",
                    headers={"Cache-Control": "public, max-age=3600"})


@router.get("/reputation/{vpa:path}/public", response_model=PublicReputationResponse)
async def get_reputation_public(
    vpa: str,
    db: AsyncSession = Depends(get_async_db),
):
    """Public (unauthenticated) reputation — tier + count buckets only."""
    try:
        result = await get_public_reputation(vpa, "UPI", db)
        return PublicReputationResponse(**result)
    except Exception as e:
        logger.error("Error getting public reputation: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to get reputation")


@router.get("/reputation/{vpa:path}", response_model=ReputationResponse)
async def get_reputation(
    vpa: str,
    db: AsyncSession = Depends(get_async_db),
):
    """Get VPA/merchant reputation with enriched scoring."""
    try:
        result = await compute_reputation(vpa, "UPI", db)
        return ReputationResponse(**result)
    except Exception as e:
        logger.error("Error getting reputation: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to get reputation")
