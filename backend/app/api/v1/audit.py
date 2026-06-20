"""Audit log verification and query endpoints."""

import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_async_db

logger = logging.getLogger(__name__)
router = APIRouter()


class VerificationResult(BaseModel):
    id: int
    valid: bool
    expected_hash: str
    actual_hash: Optional[str]


class AuditLogEntry(BaseModel):
    id: int
    user_id: Optional[int]
    action: str
    resource_type: Optional[str]
    resource_id: Optional[str]
    details: Optional[str]
    ip_address: Optional[str]
    entry_hash: Optional[str]
    created_at: str


@router.get("/audit/chain/verify", response_model=List[VerificationResult])
async def verify_audit_chain_v2(
    from_id: Optional[int] = Query(default=None),
    to_id: Optional[int] = Query(default=None),
    db: AsyncSession = Depends(get_async_db),
):
    """Alias for /audit/verify — verify audit log hash-chain integrity."""
    from app.services.audit.audit_service import verify_chain

    chain_result = await verify_chain(db, from_id=from_id, to_id=to_id)
    return [
        VerificationResult(
            id=e["id"],
            valid=e["valid"],
            expected_hash=e["expected_hash"],
            actual_hash=e["actual_hash"],
        )
        for e in chain_result.get("entries", [])
    ]


@router.get("/audit/verify", response_model=List[VerificationResult])
async def verify_audit_chain(
    from_id: Optional[int] = Query(default=None),
    to_id: Optional[int] = Query(default=None),
    db: AsyncSession = Depends(get_async_db),
):
    """Verify audit log hash-chain integrity."""
    from app.services.audit.audit_service import verify_chain

    chain_result = await verify_chain(db, from_id=from_id, to_id=to_id)
    return [
        VerificationResult(
            id=e["id"],
            valid=e["valid"],
            expected_hash=e["expected_hash"],
            actual_hash=e["actual_hash"],
        )
        for e in chain_result.get("entries", [])
    ]


@router.get("/audit/logs", response_model=List[AuditLogEntry])
async def list_audit_logs(
    user_id: Optional[int] = Query(default=None),
    action: Optional[str] = Query(default=None),
    limit: int = Query(default=100, le=500),
    db: AsyncSession = Depends(get_async_db),
):
    """Query audit log entries (admin only)."""
    from sqlalchemy import select
    from app.models.audit import AuditLog

    query = select(AuditLog).order_by(AuditLog.id.desc())
    if user_id is not None:
        query = query.filter(AuditLog.user_id == user_id)
    if action:
        query = query.filter(AuditLog.action.contains(action))
    query = query.limit(limit)

    result = await db.execute(query)
    entries = result.scalars().all()
    return [
        AuditLogEntry(
            id=e.id, user_id=e.user_id, action=e.action,
            resource_type=e.resource_type, resource_id=e.resource_id,
            details=e.details, ip_address=e.ip_address,
            entry_hash=e.entry_hash,
            created_at=e.created_at.isoformat() if e.created_at else "",
        )
        for e in entries
    ]
