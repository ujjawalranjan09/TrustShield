"""Community entity report and lookup endpoints.

Allows users to report suspicious entities (phone numbers, UPI IDs, URLs)
and look up whether an entity has been previously flagged. Uses PostgreSQL
for persistent storage via SQLAlchemy.
"""

import logging
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
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


class EntityType(str, Enum):
    """Supported entity types for reporting."""

    PHONE = "PHONE"
    UPI = "UPI"
    URL = "URL"
    EMAIL = "EMAIL"


class ReportRequest(BaseModel):
    """Payload for reporting a suspicious entity."""

    entity_value: str = Field(..., min_length=1, max_length=255)
    entity_type: EntityType
    scam_type: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=1000)
    reporter_contact: Optional[str] = Field(None, max_length=255)


class ReportResponse(BaseModel):
    """Confirmation after submitting a report."""

    report_id: str
    status: str
    message: str


class LookupResponse(BaseModel):
    """Result of an entity lookup."""

    entity_value: str
    entity_type: str
    is_flagged: bool
    report_count: int
    risk_level: str
    first_reported: Optional[str] = None
    last_seen: Optional[str] = None


class ReportStats(BaseModel):
    """Aggregate statistics for the report system."""

    total_entities_reported: int
    total_reports: int
    confirmed_fraudsters: int
    pending_review: int


class ErrorResponse(BaseModel):
    """Structured error response."""

    error: str
    detail: str
    status_code: int


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

CONFIRMATION_THRESHOLD = 3


def _compute_risk_level(report_count: int) -> str:
    """Map report count to a risk level string.

    Args:
        report_count: Number of independent reports for the entity.

    Returns:
        One of 'low', 'medium', 'high', 'critical'.
    """
    if report_count >= 10:
        return "critical"
    elif report_count >= 5:
        return "high"
    elif report_count >= 3:
        return "medium"
    elif report_count >= 1:
        return "low"
    return "low"


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post(
    "/report",
    response_model=ReportResponse,
    responses={500: {"model": ErrorResponse}},
)
async def report_entity(
    request: ReportRequest,
    db: Session = Depends(get_db),
) -> ReportResponse:
    """Report a suspicious entity to the community database.

    After 3 independent reports, the entity is marked as 'confirmed'.
    """
    try:
        report_id = str(uuid.uuid4())
        entity_key = f"{request.entity_type.value}:{request.entity_value.lower()}"

        # Find or create the flagged entity
        entity = (
            db.query(FlaggedEntity)
            .filter(FlaggedEntity.entity_value == entity_key)
            .first()
        )

        now = datetime.now(timezone.utc)

        if entity:
            entity.report_count += 1
            entity.last_seen = now
            if entity.report_count >= CONFIRMATION_THRESHOLD:
                entity.is_confirmed = 1
            report_count = entity.report_count
        else:
            entity = FlaggedEntity(
                entity_value=entity_key,
                entity_type=request.entity_type.value,
                scam_type=request.scam_type,
                description=request.description,
                report_count=1,
                is_confirmed=0,
                first_reported=now,
                last_seen=now,
            )
            db.add(entity)
            report_count = 1

        # Create individual report record
        report = EntityReport(
            report_id=report_id,
            entity_id=entity.id if entity.id else None,
            reporter_contact=request.reporter_contact,
            scam_type=request.scam_type,
            description=request.description,
            created_at=now,
        )
        db.add(report)
        db.commit()

        status = "confirmed" if report_count >= CONFIRMATION_THRESHOLD else "pending"

        logger.info(
            "Entity reported: %s (total reports: %d, status: %s)",
            entity_key,
            report_count,
            status,
        )

        return ReportResponse(
            report_id=report_id,
            status=status,
            message=f"Report submitted. Entity has {report_count} report(s). Status: {status}",
        )

    except Exception as e:
        db.rollback()
        logger.error("Error reporting entity: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to submit report")


@router.get(
    "/lookup/{entity_type}/{entity_value}",
    response_model=LookupResponse,
    responses={500: {"model": ErrorResponse}},
)
async def lookup_entity(
    entity_type: EntityType,
    entity_value: str,
    db: Session = Depends(get_db),
) -> LookupResponse:
    """Look up an entity to check if it has been reported as fraudulent."""
    try:
        entity_key = f"{entity_type.value}:{entity_value.lower()}"

        entity = (
            db.query(FlaggedEntity)
            .filter(FlaggedEntity.entity_value == entity_key)
            .first()
        )

        if entity:
            return LookupResponse(
                entity_value=entity.entity_value,
                entity_type=entity.entity_type,
                is_flagged=entity.is_confirmed == 1,
                report_count=entity.report_count,
                risk_level=_compute_risk_level(entity.report_count),
                first_reported=entity.first_reported.isoformat()
                if entity.first_reported
                else None,
                last_seen=entity.last_seen.isoformat() if entity.last_seen else None,
            )

        return LookupResponse(
            entity_value=entity_value,
            entity_type=entity_type.value,
            is_flagged=False,
            report_count=0,
            risk_level="low",
        )

    except Exception as e:
        logger.error("Error looking up entity: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to look up entity")


@router.get(
    "/reports/stats",
    response_model=ReportStats,
    responses={500: {"model": ErrorResponse}},
)
async def get_report_stats(db: Session = Depends(get_db)) -> ReportStats:
    """Get aggregate statistics about reported entities."""
    try:
        total_entities = db.query(func.count(FlaggedEntity.id)).scalar() or 0
        total_reports = db.query(
            func.coalesce(func.sum(FlaggedEntity.report_count), 0)
        ).scalar()
        confirmed = (
            db.query(func.count(FlaggedEntity.id))
            .filter(FlaggedEntity.is_confirmed == 1)
            .scalar()
        ) or 0

        return ReportStats(
            total_entities_reported=total_entities,
            total_reports=total_reports,
            confirmed_fraudsters=confirmed,
            pending_review=total_entities - confirmed,
        )

    except Exception as e:
        logger.error("Error fetching report stats: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch stats")
