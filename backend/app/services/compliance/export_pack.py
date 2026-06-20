"""Regulator export pack — CSV + manifest + ZIP."""

import csv
import hashlib
import hmac
import io
import json
import logging
import zipfile
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings

logger = logging.getLogger(__name__)


def _mask_pii(value: str, mask_type: str = "phone") -> str:
    if not value:
        return ""
    if mask_type == "phone" and len(value) >= 4:
        return value[:2] + "****" + value[-2:]
    if mask_type == "upi" and "@" in value:
        local, domain = value.split("@", 1)
        return local[0] + "***@" + domain
    return value[:3] + "***"


async def generate_entities_csv(db: AsyncSession) -> str:
    from app.models.entity import FlaggedEntity
    result = await db.execute(
        select(FlaggedEntity).order_by(FlaggedEntity.id.desc()).limit(10000)
    )
    entities = result.scalars().all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["entity_value_masked", "entity_type", "scam_type", "report_count", "risk_level", "first_reported", "last_seen"])

    for e in entities:
        mask_type = "upi" if "UPI" in (e.entity_type or "") else "phone"
        writer.writerow([
            _mask_pii(e.entity_value, mask_type),
            e.entity_type, e.scam_type, e.report_count,
            "critical" if e.report_count >= 10 else "high" if e.report_count >= 5 else "medium" if e.report_count >= 3 else "low",
            e.first_reported.isoformat() if e.first_reported else "",
            e.last_seen.isoformat() if e.last_seen else "",
        ])
    return output.getvalue()


async def generate_sessions_csv(db: AsyncSession, quarter: str) -> str:
    from app.models.scan_event import ScanEvent
    start, end = _quarter_to_dates(quarter)

    result = await db.execute(
        select(ScanEvent).filter(
            ScanEvent.created_at >= start, ScanEvent.created_at < end
        ).order_by(ScanEvent.id.desc()).limit(10000)
    )
    sessions = result.scalars().all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["session_id", "scan_type", "risk_score", "risk_level", "action_taken", "processing_time_ms", "created_at"])

    for s in sessions:
        writer.writerow([
            s.session_id, s.scan_type, s.risk_score, s.risk_level,
            s.action_taken, s.processing_time_ms,
            s.created_at.isoformat() if s.created_at else "",
        ])
    return output.getvalue()


async def generate_feedback_csv(db: AsyncSession) -> str:
    from app.models.feedback import FeedbackLabel
    result = await db.execute(select(FeedbackLabel).order_by(FeedbackLabel.id.desc()).limit(10000))
    labels = result.scalars().all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["session_id", "original_risk_score", "original_risk_level", "analyst_label", "created_at"])

    for f in labels:
        writer.writerow([
            f.session_id, f.original_risk_score, f.original_risk_level,
            f.analyst_label, f.created_at.isoformat() if f.created_at else "",
        ])
    return output.getvalue()


async def generate_audit_csv(db: AsyncSession) -> str:
    from app.models.audit import AuditLog
    result = await db.execute(select(AuditLog).order_by(AuditLog.id.desc()).limit(10000))
    logs = result.scalars().all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["id", "user_id", "action", "resource_type", "ip_address", "entry_hash", "created_at"])

    for l in logs:
        writer.writerow([
            l.id, l.user_id, l.action, l.resource_type, l.ip_address,
            l.entry_hash, l.created_at.isoformat() if l.created_at else "",
        ])
    return output.getvalue()


def _quarter_to_dates(quarter: str) -> tuple:
    from datetime import datetime, timezone
    try:
        parts = quarter.split("_")
        q = int(parts[0].replace("Q", ""))
        year = int(parts[1])
        start_month = (q - 1) * 3 + 1
        start = datetime(year, start_month, 1, tzinfo=timezone.utc)
        end_month = start_month + 3
        if end_month > 12:
            end = datetime(year + 1, 1, 1, tzinfo=timezone.utc)
        else:
            end = datetime(year, end_month, 1, tzinfo=timezone.utc)
        return start, end
    except Exception:
        now = datetime.now(timezone.utc)
        return now.replace(month=1, day=1), now


def _compute_file_hash(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


async def generate_drift_report_csv(db: AsyncSession, quarter: str) -> str:
    """Generate drift log CSV for the quarter."""
    from app.models.drift import DriftLog
    start, end = _quarter_to_dates(quarter)

    result = await db.execute(
        select(DriftLog).filter(
            DriftLog.created_at >= start, DriftLog.created_at < end
        ).order_by(DriftLog.created_at.desc()).limit(5000)
    )
    logs = result.scalars().all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["feature_name", "psi_value", "alert_triggered", "model_version", "created_at"])
    for l in logs:
        writer.writerow([
            l.feature_name, l.psi_value, l.alert_triggered, l.model_version,
            l.created_at.isoformat() if l.created_at else "",
        ])
    return output.getvalue()


async def generate_audit_verification_csv(db: AsyncSession) -> Tuple[str, bool]:
    """Run audit-chain verification and return CSV + validity."""
    from app.services.audit.audit_service import verify_chain

    result = await verify_chain(db)
    entries = result.get("entries", [])

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["entry_id", "valid", "expected_hash", "actual_hash"])
    for entry in entries:
        writer.writerow([
            entry.get("id", ""),
            entry.get("valid", False),
            entry.get("expected_hash", ""),
            entry.get("actual_hash", ""),
        ])

    return output.getvalue(), result.get("valid", True)


async def generate_dpdp_register_csv(db: AsyncSession) -> str:
    """Generate DPDP data register CSV."""
    from app.models.compliance import DataAsset

    result = await db.execute(
        select(DataAsset).order_by(DataAsset.table_name, DataAsset.asset_name)
    )
    assets = result.scalars().all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["asset_name", "table_name", "pii_category", "lawful_basis", "retention_policy", "last_reviewed"])
    for a in assets:
        writer.writerow([
            a.asset_name, a.table_name, a.pii_category, a.lawful_basis,
            a.retention_policy,
            a.last_reviewed.isoformat() if a.last_reviewed else "",
        ])
    return output.getvalue()


def _sign_manifest(manifest: dict, admin_id: int = 0, timestamp: str = "") -> str:
    """Sign manifest with admin attribution."""
    key = settings.export_signing_key
    if not key:
        logger.error(
            "EXPORT_SIGNING_KEY not set — regulator manifest signature is invalid. "
            "Set EXPORT_SIGNING_KEY before generating regulator packs."
        )
        key = "UNCONFIGURED-DO-NOT-VERIFY"
    meta = {
        "signed_by_admin_id": admin_id,
        "signed_at": timestamp or datetime.now(timezone.utc).isoformat(),
    }
    payload = json.dumps(manifest, sort_keys=True) + json.dumps(meta, sort_keys=True)
    return hmac.new(key.encode(), payload.encode(), hashlib.sha256).hexdigest()


async def generate_regulator_pack(
    db: AsyncSession,
    quarter: str,
    signed_by_admin_id: int = 0,
    include_gold_report: bool = True,
) -> bytes:
    """Generate ZIP archive with all compliance artifacts + signed manifest.

    Includes:
    - entities.csv, sessions.csv, feedback.csv, audit.csv (existing)
    - audit_verification.csv (B3.1)
    - drift_report.csv (B2.5)
    - gold_report.json (B2.3) — if available
    - dpdp_register.csv (B3.2)
    - manifest.json with file hashes + signature
    - cover.pdf (optional, reuse RBIReportBuilder)
    """
    buf = io.BytesIO()
    entities_csv = await generate_entities_csv(db)
    sessions_csv = await generate_sessions_csv(db, quarter)
    feedback_csv = await generate_feedback_csv(db)
    audit_csv = await generate_audit_csv(db)
    audit_verification_csv, chain_valid = await generate_audit_verification_csv(db)
    drift_csv = await generate_drift_report_csv(db, quarter)
    dpdp_csv = await generate_dpdp_register_csv(db)

    manifest = {
        "quarter": quarter,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "chain_valid": chain_valid,
        "files": {},
    }

    files_to_include: List[Tuple[str, bytes]] = [
        ("entities.csv", entities_csv.encode()),
        ("sessions.csv", sessions_csv.encode()),
        ("feedback.csv", feedback_csv.encode()),
        ("audit.csv", audit_csv.encode()),
        ("audit_verification.csv", audit_verification_csv.encode()),
        ("drift_report.csv", drift_csv.encode()),
        ("dpdp_register.csv", dpdp_csv.encode()),
    ]

    # Include gold_report.json if available
    if include_gold_report:
        try:
            from pathlib import Path
            gold_path = Path(__file__).resolve().parents[4] / "gold_report.json"
            if gold_path.exists():
                with open(gold_path) as f:
                    gold_data = f.read()
                files_to_include.append(("gold_report.json", gold_data.encode()))
        except Exception:
            pass

    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, content in files_to_include:
            zf.writestr(name, content)
            manifest["files"][name] = _compute_file_hash(content)

        # Add cover PDF if RBIReportBuilder produces one
        try:
            from app.services.compliance.rbi_report_builder import RBIReportBuilder
            builder = RBIReportBuilder(db=db)
            cover_pdf = await builder.build_pdf(quarter)
            zf.writestr("cover.pdf", cover_pdf)
            manifest["files"]["cover.pdf"] = _compute_file_hash(cover_pdf)
        except Exception as exc:
            logger.warning("Cover PDF generation skipped: %s", exc)

        # Sign manifest with admin attribution
        sign_timestamp = manifest["generated_at"]
        manifest["signature"] = _sign_manifest(manifest, signed_by_admin_id, sign_timestamp)
        zf.writestr("manifest.json", json.dumps(manifest, indent=2))

    buf.seek(0)
    return buf.getvalue()
