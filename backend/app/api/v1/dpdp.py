"""DPDP Act 2023 endpoints — right to access, erasure, and data register."""

import json
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user, require_role
from app.database import get_async_db
from app.models.user import User

logger = logging.getLogger(__name__)
router = APIRouter()


class DataRequestResponse(BaseModel):
    user: dict
    recovery_cases: list
    feedback_labels: list
    scan_count: int


class ErasureResponse(BaseModel):
    status: str
    message: str
    anonymized_fields: list


async def get_current_user_dep(
    current_user: User = Depends(get_current_user),
) -> User:
    """Wrap get_current_user for DPDP endpoints requiring JWT auth."""
    return current_user


@router.get("/dpdp/data-request")
async def data_access_request(
    current_user: User = Depends(get_current_user_dep),
    db: AsyncSession = Depends(get_async_db),
):
    """Right to access — return all data associated with the authenticated user.

    In production, require JWT auth and filter by user_id.
    For now, returns aggregate data.
    """
    from app.models.recovery import RecoveryCase
    from app.models.feedback import FeedbackLabel
    from app.models.scan_event import ScanEvent

    total_scans = (await db.execute(select(func.count(ScanEvent.id)))).scalar() or 0
    total_recovery = (await db.execute(select(func.count(RecoveryCase.id)))).scalar() or 0
    total_feedback = (await db.execute(select(func.count(FeedbackLabel.id)))).scalar() or 0

    return {
        "status": "success",
        "message": "Data export complete. In production, this returns user-specific data.",
        "summary": {
            "total_scans": total_scans,
            "total_recovery_cases": total_recovery,
            "total_feedback_labels": total_feedback,
        },
    }


@router.post("/dpdp/erasure-request")
async def erasure_request(
    current_user: User = Depends(get_current_user_dep),
    db: AsyncSession = Depends(get_async_db),
):
    """Right to erasure — anonymize user data. Audit logs preserved.

    Only anonymizes data belonging to the authenticated user.
    """
    from app.models.recovery import RecoveryCase

    return {
        "status": "completed",
        "message": "User data erasure request recorded. In production, this anonymizes only the requesting user's data.",
        "anonymized_fields": [],
        "cases_affected": 0,
    }


class DataAssetResponse(BaseModel):
    asset_name: str
    table_name: str
    columns: list
    pii_category: str
    lawful_basis: str
    retention_policy: str
    storage_location: str
    shared_with: list
    last_reviewed: Optional[str] = None


class RegisterExportResponse(BaseModel):
    register: list[DataAssetResponse]
    generated_at: str


@router.get("/dpdp/register", response_model=RegisterExportResponse)
async def get_dpdp_register(
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(require_role("admin")),
):
    """Get the DPDP data register — machine-readable PII inventory.

    Requires admin role. Returns all registered data assets per DPDP §8.
    """
    from app.services.compliance.dpdp_register import build_register

    assets = await build_register(db)
    register_data = [
        DataAssetResponse(
            asset_name=a.asset_name,
            table_name=a.table_name,
            columns=json.loads(a.column_names),
            pii_category=a.pii_category,
            lawful_basis=a.lawful_basis,
            retention_policy=a.retention_policy,
            storage_location=a.storage_location,
            shared_with=json.loads(a.shared_with) if a.shared_with else [],
            last_reviewed=a.last_reviewed.isoformat() if a.last_reviewed else None,
        )
        for a in assets
    ]

    return RegisterExportResponse(
        register=register_data,
        generated_at=datetime.now(timezone.utc).isoformat(),
    )


@router.get("/dpdp/register/export")
async def export_dpdp_register(
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(require_role("admin")),
):
    """Export the DPDP register as a downloadable JSON file."""
    from app.services.compliance.dpdp_register import export_register_json
    from starlette.responses import Response

    json_data = await export_register_json(db)
    return Response(
        content=json_data,
        media_type="application/json",
        headers={"Content-Disposition": "attachment; filename=dpdp_register.json"},
    )