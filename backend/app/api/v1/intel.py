"""Multi-Bank Fraud Intelligence Network endpoint — DB-backed."""

import hashlib
import hmac
import json
import logging
import secrets
import uuid
from datetime import datetime, timezone
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_async_db
from app.models.intel import Bank, CrossBankReport, SharedEntity
from app.schemas.intel import (
    BankRegistrationRequest,
    BankRegistrationResponse,
    CrossBankLookupRequest,
    CrossBankLookupResponse,
    NetworkStats,
    ShareEntityRequest,
    ShareEntityResponse,
)

logger = logging.getLogger(__name__)
router = APIRouter()


async def verify_bank_api_key(
    x_api_key: str = Header(..., description="Bank API key"),
    db: AsyncSession = Depends(get_async_db),
) -> Bank:
    """Authenticate bank via API key using constant-time hash comparison."""
    # Hash the incoming key the same way we store it
    api_key_hash = hashlib.sha256(x_api_key.encode()).hexdigest()
    result = await db.execute(select(Bank))
    banks = result.scalars().all()
    for bank in banks:
        if bank.is_active and hmac.compare_digest(bank.api_key_hash, api_key_hash):
            return bank
    raise HTTPException(status_code=401, detail="Invalid or inactive bank API key")


def _hash_entity(value: str) -> str:
    return hashlib.sha256(value.lower().strip().encode()).hexdigest()[:32]


async def _compute_cross_bank_risk(entity_hash: str, db: AsyncSession) -> tuple[float, int, int, List[str]]:
    result = await db.execute(select(SharedEntity).filter(SharedEntity.entity_hash == entity_hash))
    entity = result.scalars().first()
    if not entity:
        return 0.0, 0, 0, []

    result = await db.execute(select(CrossBankReport).filter(CrossBankReport.entity_hash == entity_hash))
    reports = result.scalars().all()
    total = sum(r.incident_count for r in reports)
    banks = len(set(r.bank_id for r in reports))
    scam_types = list(set(r.scam_type for r in reports))

    report_factor = min(1.0, total / 20.0)
    diversity_factor = min(1.0, banks / 5.0)
    score = round((report_factor * 0.6 + diversity_factor * 0.4) * 100, 1)

    entity.total_reports = total
    entity.banks_reporting = banks
    entity.cross_bank_risk_score = score
    entity.scam_types = json.dumps(scam_types)
    entity.last_updated = datetime.now(timezone.utc)

    return score, total, banks, scam_types


@router.post("/intel/register-bank", response_model=BankRegistrationResponse)
async def register_bank(request: BankRegistrationRequest, db: AsyncSession = Depends(get_async_db)):
    result = await db.execute(select(Bank).filter(Bank.bank_code == request.bank_code.upper()))
    existing = result.scalars().first()
    if existing:
        raise HTTPException(status_code=400, detail=f"Bank code '{request.bank_code}' already registered")

    bank_id = str(uuid.uuid4())
    api_key = f"ts_bank_{secrets.token_urlsafe(32)}"
    api_key_hash = hashlib.sha256(api_key.encode()).hexdigest()

    bank = Bank(
        bank_id=bank_id, bank_name=request.bank_name, bank_code=request.bank_code.upper(),
        contact_email=request.contact_email, contact_name=request.contact_name, api_key_hash=api_key_hash,
    )
    db.add(bank)
    await db.commit()

    logger.info("Bank registered: %s (%s)", request.bank_name, request.bank_code)
    return BankRegistrationResponse(bank_id=bank_id, bank_name=request.bank_name, api_key=api_key,
                                    message="Bank registered successfully. Store the API key securely — it cannot be retrieved again.")


@router.post("/intel/share-entity", response_model=ShareEntityResponse)
async def share_entity(
    request: ShareEntityRequest,
    bank: Bank = Depends(verify_bank_api_key),
    db: AsyncSession = Depends(get_async_db),
):
    entity_hash = _hash_entity(request.entity_value)
    now = datetime.now(timezone.utc)

    result = await db.execute(select(SharedEntity).filter(SharedEntity.entity_hash == entity_hash))
    entity = result.scalars().first()
    if not entity:
        entity = SharedEntity(entity_hash=entity_hash, entity_type=request.entity_type, first_shared=now)
        db.add(entity)
        await db.flush()

    report = CrossBankReport(
        entity_hash=entity_hash, bank_id=bank.bank_id, scam_type=request.scam_type,
        risk_score=request.risk_score, incident_count=request.incident_count, notes=request.notes,
    )
    db.add(report)
    await db.commit()

    score, total, banks_count, scam_types = await _compute_cross_bank_risk(entity_hash, db)
    await db.commit()

    logger.info("Entity shared by %s: hash=%s score=%.1f reports=%d", bank.bank_code, entity_hash[:16], score, total)
    return ShareEntityResponse(shared_id=str(uuid.uuid4()), cross_bank_risk_score=score,
                               total_reports=total, banks_reporting=banks_count,
                               message="Entity shared with the intelligence network.")


@router.post("/intel/lookup", response_model=CrossBankLookupResponse)
async def cross_bank_lookup(
    request: CrossBankLookupRequest,
    bank: Bank = Depends(verify_bank_api_key),
    db: AsyncSession = Depends(get_async_db),
):
    entity_hash = _hash_entity(request.entity_value)
    score, total, banks_count, scam_types = await _compute_cross_bank_risk(entity_hash, db)
    risk_level = "critical" if score >= 70 else "high" if score >= 50 else "medium" if score >= 30 else "low"
    return CrossBankLookupResponse(entity_hash=entity_hash, entity_type=request.entity_type,
                                    is_known_fraudster=total >= 3, cross_bank_risk_score=score,
                                    total_reports=total, banks_reporting=banks_count, scam_types=scam_types,
                                    risk_level=risk_level)


@router.get("/intel/stats", response_model=NetworkStats)
async def get_network_stats(bank: Bank = Depends(verify_bank_api_key), db: AsyncSession = Depends(get_async_db)):
    return NetworkStats(
        registered_banks=(await db.execute(select(func.count(Bank.id)))).scalar() or 0,
        shared_entities=(await db.execute(select(func.count(SharedEntity.id)))).scalar() or 0,
        total_cross_bank_reports=(await db.execute(select(func.count(CrossBankReport.id)))).scalar() or 0,
        active_alerts=0,
    )
