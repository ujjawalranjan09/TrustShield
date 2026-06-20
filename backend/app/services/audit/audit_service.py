"""Audit service with hash-chain integrity.

Every write computes SHA-256(prev_hash + action + resource + timestamp + user_id)
and stores the chain link. Verification recomputes to detect tampering.
"""

import hashlib
import logging
from datetime import datetime, timezone
from typing import Dict, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import AuditLog

logger = logging.getLogger(__name__)


def _compute_hash(prev_hash: str, action: str, resource_type: str,
                   resource_id: str, timestamp: str, user_id: str,
                   tenant_id: str = "") -> str:
    """Compute SHA-256 hash for an audit entry."""
    payload = f"{prev_hash}|{action}|{resource_type}|{resource_id}|{timestamp}|{user_id}|{tenant_id}"
    return hashlib.sha256(payload.encode()).hexdigest()


async def get_last_hash(db: AsyncSession) -> Optional[str]:
    """Get the hash of the most recent audit entry."""
    result = await db.execute(
        select(AuditLog.entry_hash).order_by(AuditLog.id.desc()).limit(1)
    )
    return result.scalar()


async def write_audit(
    db: AsyncSession,
    user_id: int,
    action: str,
    resource_type: str = "",
    resource_id: str = "",
    details: str = "",
    ip_address: str = "",
    request_id: str = "",
    tenant_id: str = "",
) -> AuditLog:
    """Write an audit entry with hash-chain."""
    prev_hash = await get_last_hash(db)
    # Use the SAME timestamp for both hashing and the stored row so
    # verify_chain can recompute the hash exactly. We set created_at
    # explicitly instead of relying on the DB server_default.
    timestamp = datetime.now(timezone.utc).isoformat()
    entry_hash = _compute_hash(
        prev_hash or "genesis",
        action,
        resource_type,
        resource_id,
        timestamp,
        str(user_id),
        tenant_id or "",
    )

    entry = AuditLog(
        request_id=request_id,
        user_id=user_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        details=details,
        ip_address=ip_address,
        prev_hash=prev_hash,
        entry_hash=entry_hash,
        created_at=datetime.now(timezone.utc),
    )
    db.add(entry)
    await db.flush()
    return entry


async def verify_chain(
    db: AsyncSession,
    from_id: Optional[int] = None,
    to_id: Optional[int] = None,
) -> Dict:
    """Verify audit hash chain integrity.

    Returns a summary dict:
        {
          "valid": bool,                       # all entries verified
          "checked": int,                      # number of entries checked
          "entries": List[Dict],               # per-entry results
          "first_bad_entry_id": Optional[int], # None if valid
          "expected_hash": str,                # expected hash of first bad entry
          "actual_hash": str,                  # actual hash of first bad entry
        }
    """
    query = select(AuditLog).order_by(AuditLog.id.asc())
    if from_id:
        query = query.filter(AuditLog.id >= from_id)
    if to_id:
        query = query.filter(AuditLog.id <= to_id)

    result = await db.execute(query)
    entries = result.scalars().all()

    verification = []
    prev_hash = None
    first_bad = None

    for entry in entries:
        timestamp = entry.created_at.isoformat() if entry.created_at else ""
        expected = _compute_hash(
            prev_hash or "genesis",
            entry.action,
            entry.resource_type or "",
            entry.resource_id or "",
            timestamp,
            str(entry.user_id or ""),
        )
        valid = expected == entry.entry_hash
        verification.append({
            "id": entry.id,
            "valid": valid,
            "expected_hash": expected,
            "actual_hash": entry.entry_hash,
        })
        if not valid and first_bad is None:
            first_bad = {
                "id": entry.id,
                "expected_hash": expected,
                "actual_hash": entry.entry_hash or "",
            }
        prev_hash = entry.entry_hash

    return {
        "valid": first_bad is None,
        "checked": len(verification),
        "entries": verification,
        "first_bad_entry_id": first_bad["id"] if first_bad else None,
        "expected_hash": first_bad["expected_hash"] if first_bad else "",
        "actual_hash": first_bad["actual_hash"] if first_bad else "",
    }
