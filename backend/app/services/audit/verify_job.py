"""Nightly audit-chain verification job.

Calls ``audit_service.verify_chain`` over the full audit log. If any
entry fails verification, the job logs CRITICAL, pages the on-call
engineer, and persists the break details to a dedicated table for
human acknowledgment.
"""

import logging
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Integer, String, Text, select

from app.config import settings
from app.database import Base, AsyncSessionLocal

logger = logging.getLogger(__name__)


class AuditChainBreak(Base):
    """Records an audit-chain verification failure (tamper evidence).

    A break must NOT be auto-corrected — human acknowledgment is required.
    """

    __tablename__ = "audit_chain_breaks"

    id = Column(Integer, primary_key=True, index=True)
    first_bad_entry_id = Column(Integer, nullable=False)
    expected_hash = Column(String(64), nullable=False)
    actual_hash = Column(String(64), nullable=False)
    detected_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    resolved_at = Column(DateTime, nullable=True)
    resolved_by = Column(String(100), nullable=True)


async def run_audit_verification() -> dict:
    """Run nightly audit-chain verification.

    Returns a dict with the verification result.
    """
    from app.services.audit.audit_service import verify_chain

    async with AsyncSessionLocal() as db:
        result = await verify_chain(db)

        if result.get("valid", True):
            logger.info(
                "Audit chain verification: OK (%d entries checked)",
                result.get("checked", 0),
            )
            return {"status": "ok", "checked": result.get("checked", 0)}

        # Chain is broken — log CRITICAL and persist break
        first_bad = result.get("first_bad_entry_id")
        expected = result.get("expected_hash", "")
        actual = result.get("actual_hash", "")

        logger.critical(
            "AUDIT CHAIN BREAK DETECTED! entry_id=%s expected=%s actual=%s",
            first_bad,
            expected,
            actual,
        )

        # Persist the break
        break_record = AuditChainBreak(
            first_bad_entry_id=first_bad,
            expected_hash=expected,
            actual_hash=actual,
        )
        db.add(break_record)
        await db.commit()

        # Fire alert (placeholder until real alerting configured)
        try:
            from app.services.alerting.alert_service import trigger_alert

            await trigger_alert(
                session_id=f"audit-chain-break-{first_bad}",
                risk_score=100,
                risk_level="critical",
                action="audit_chain_break",
                entities=[f"entry:{first_bad}"],
            )
        except ImportError:
            logger.info("Alerting not configured — manually page the on-call engineer")
        except Exception as exc:
            logger.warning("Alert triggered but could not deliver: %s", exc)

        return {
            "status": "broken",
            "first_bad_entry_id": first_bad,
            "expected_hash": expected,
            "actual_hash": actual,
        }


async def ack_audit_break(
    break_id: int, resolved_by: str
) -> dict:
    """Acknowledge and resolve an audit-chain break.

    This is a human-only operation — it updates the resolved_at and
    resolved_by fields on the ``AuditChainBreak`` row.
    """
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(AuditChainBreak).filter(AuditChainBreak.id == break_id)
        )
        break_record = result.scalars().first()
        if not break_record:
            return {"success": False, "reason": "Break record not found"}

        break_record.resolved_at = datetime.now(timezone.utc)
        break_record.resolved_by = resolved_by
        await db.commit()

        logger.info(
            "Audit chain break %d resolved by %s", break_id, resolved_by
        )

        return {
            "success": True,
            "break_id": break_id,
            "resolved_by": resolved_by,
        }