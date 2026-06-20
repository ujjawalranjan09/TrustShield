"""Community entity report and lookup endpoints."""

import logging
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_async_db
from app.models.entity import EntityReport, FlaggedEntity

logger = logging.getLogger(__name__)

router = APIRouter()


class EntityType(str, Enum):
    PHONE = "PHONE"
    UPI = "UPI"
    URL = "URL"
    EMAIL = "EMAIL"


class ReportRequest(BaseModel):
    entity_value: str = Field(..., min_length=1, max_length=255)
    entity_type: EntityType
    scam_type: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=1000)
    reporter_contact: Optional[str] = Field(None, max_length=255)


class ReportResponse(BaseModel):
    report_id: str
    status: str
    message: str


class LookupResponse(BaseModel):
    entity_value: str
    entity_type: str
    is_flagged: bool
    report_count: int
    risk_level: str
    first_reported: Optional[str] = None
    last_seen: Optional[str] = None


class ReportStats(BaseModel):
    total_entities_reported: int
    total_reports: int
    confirmed_fraudsters: int
    pending_review: int


class ErrorResponse(BaseModel):
    error: str
    detail: str
    status_code: int


CONFIRMATION_THRESHOLD = 3


def _compute_risk_level(report_count: int) -> str:
    if report_count >= 10:
        return "critical"
    elif report_count >= 5:
        return "high"
    elif report_count >= 3:
        return "medium"
    return "low"


@router.post(
    "/report",
    response_model=ReportResponse,
    status_code=201,
    responses={500: {"model": ErrorResponse}},
)
async def report_entity(
    request: ReportRequest,
    db: AsyncSession = Depends(get_async_db),
) -> ReportResponse:
    """Report a suspicious entity to the community database."""
    try:
        report_id = str(uuid.uuid4())
        entity_key = f"{request.entity_type.value}:{request.entity_value.lower()}"

        result = await db.execute(select(FlaggedEntity).filter(FlaggedEntity.entity_value == entity_key))
        entity = result.scalars().first()

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

        report = EntityReport(
            report_id=report_id,
            entity_id=entity.id if entity.id else None,
            reporter_contact=request.reporter_contact,
            scam_type=request.scam_type,
            description=request.description,
            created_at=now,
        )
        db.add(report)
        await db.commit()

        status = "confirmed" if report_count >= CONFIRMATION_THRESHOLD else "pending"

        logger.info("Entity reported: %s (total reports: %d, status: %s)", entity_key, report_count, status)

        return ReportResponse(
            report_id=report_id,
            status=status,
            message=f"Report submitted. Entity has {report_count} report(s). Status: {status}",
        )

    except Exception as e:
        await db.rollback()
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
    db: AsyncSession = Depends(get_async_db),
) -> LookupResponse:
    """Look up an entity to check if it has been reported as fraudulent."""
    try:
        entity_key = f"{entity_type.value}:{entity_value.lower()}"

        result = await db.execute(select(FlaggedEntity).filter(FlaggedEntity.entity_value == entity_key))
        entity = result.scalars().first()

        if entity:
            return LookupResponse(
                entity_value=entity.entity_value,
                entity_type=entity.entity_type,
                is_flagged=entity.is_confirmed == 1,
                report_count=entity.report_count,
                risk_level=_compute_risk_level(entity.report_count),
                first_reported=entity.first_reported.isoformat() if entity.first_reported else None,
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
async def get_report_stats(db: AsyncSession = Depends(get_async_db)) -> ReportStats:
    """Get aggregate statistics about reported entities."""
    try:
        total_entities = (await db.execute(select(func.count(FlaggedEntity.id)))).scalar() or 0
        total_reports = (await db.execute(select(func.coalesce(func.sum(FlaggedEntity.report_count), 0)))).scalar()
        confirmed = (await db.execute(
            select(func.count(FlaggedEntity.id)).filter(FlaggedEntity.is_confirmed == 1)
        )).scalar() or 0

        return ReportStats(
            total_entities_reported=total_entities,
            total_reports=total_reports,
            confirmed_fraudsters=confirmed,
            pending_review=total_entities - confirmed,
        )

    except Exception as e:
        logger.error("Error fetching report stats: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch stats")


@router.get("/reports/rbi/{quarter}")
async def download_rbi_report(
    quarter: str,
    client_id: str = "default",
    db: AsyncSession = Depends(get_async_db),
):
    """Generate and download RBI quarterly compliance report."""
    from fastapi.responses import StreamingResponse
    from app.services.compliance.rbi_report_builder import RBIReportBuilder

    builder = RBIReportBuilder(db=db)
    pdf_bytes = await builder.generate_quarterly_report(client_id, quarter)

    return StreamingResponse(
        iter([pdf_bytes]),
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=rbi-report-{quarter}.pdf"},
    )


@router.get("/reports/regulator/{quarter}")
async def download_regulator_pack(
    quarter: str,
    db: AsyncSession = Depends(get_async_db),
):
    """Generate and download regulator export pack (ZIP with PDF + CSVs + manifest)."""
    from fastapi.responses import StreamingResponse
    from app.services.compliance.export_pack import generate_regulator_pack

    zip_bytes = await generate_regulator_pack(db, quarter)

    return StreamingResponse(
        iter([zip_bytes]),
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename=regulator-pack-{quarter}.zip"},
    )
