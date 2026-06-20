"""DPDP data register service — inventory of PII assets (DPDP §8).

Provides functions to build, query, and export the data register.
"""

import json
import logging
from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.compliance import DataAsset

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Seed data — curated inventory of all PII assets in the system
# ---------------------------------------------------------------------------

SEED_ASSETS = [
    {
        "asset_name": "recovery_cases.victim_name",
        "table_name": "recovery_cases",
        "column_names": '["victim_name"]',
        "pii_category": "identity",
        "lawful_basis": "legal_obligation",
        "retention_policy": "7 years per RBI, then anonymized",
        "storage_location": "ap-south-1 RDS, encrypted at rest",
        "shared_with": '["bank_partner", "cybercrime_portal"]',
    },
    {
        "asset_name": "recovery_cases.victim_phone",
        "table_name": "recovery_cases",
        "column_names": '["victim_phone"]',
        "pii_category": "contact",
        "lawful_basis": "legal_obligation",
        "retention_policy": "7 years per RBI, then anonymized",
        "storage_location": "ap-south-1 RDS, encrypted at rest",
        "shared_with": '["bank_partner", "cybercrime_portal"]',
    },
    {
        "asset_name": "recovery_cases.scammer_info",
        "table_name": "recovery_cases",
        "column_names": '["scammer_info"]',
        "pii_category": "identity",
        "lawful_basis": "legitimate_interest",
        "retention_policy": "7 years per RBI, then anonymized",
        "storage_location": "ap-south-1 RDS, encrypted at rest",
        "shared_with": '["intel_network"]',
    },
    {
        "asset_name": "recovery_cases.upi_id",
        "table_name": "recovery_cases",
        "column_names": '["upi_id"]',
        "pii_category": "financial",
        "lawful_basis": "legal_obligation",
        "retention_policy": "7 years per RBI, then anonymized",
        "storage_location": "ap-south-1 RDS, encrypted at rest",
        "shared_with": '["bank_partner"]',
    },
    {
        "asset_name": "feedback_labels.analyst_email",
        "table_name": "feedback_labels",
        "column_names": '["analyst_email"]',
        "pii_category": "contact",
        "lawful_basis": "consent",
        "retention_policy": "2 years after last activity, then deleted",
        "storage_location": "ap-south-1 RDS, encrypted at rest",
        "shared_with": "[]",
    },
    {
        "asset_name": "behavioral_signals.device_fingerprint",
        "table_name": "behavioral_signals",
        "column_names": '["device_fingerprint", "ip_address"]',
        "pii_category": "behavioral",
        "lawful_basis": "legitimate_interest",
        "retention_policy": "180 days per config, then purged",
        "storage_location": "ap-south-1 RDS, encrypted at rest",
        "shared_with": "[]",
    },
    {
        "asset_name": "scan_events.session_id",
        "table_name": "scan_events",
        "column_names": '["session_id", "client_ip"]',
        "pii_category": "behavioral",
        "lawful_basis": "legitimate_interest",
        "retention_policy": "730 days, then purged",
        "storage_location": "ap-south-1 RDS, encrypted at rest",
        "shared_with": "[]",
    },
    {
        "asset_name": "intel_entities.hashed_value",
        "table_name": "flagged_entities",
        "column_names": '["entity_value"]',
        "pii_category": "identity",
        "lawful_basis": "legitimate_interest",
        "retention_policy": "Indefinite (hashed, not raw)",
        "storage_location": "ap-south-1 RDS, encrypted at rest",
        "shared_with": '["intel_network"]',
    },
    {
        "asset_name": "audit_logs.user_id",
        "table_name": "audit_logs",
        "column_names": '["user_id", "ip_address"]',
        "pii_category": "behavioral",
        "lawful_basis": "legal_obligation",
        "retention_policy": "Indefinite (hash-chain integrity required)",
        "storage_location": "ap-south-1 RDS, encrypted at rest",
        "shared_with": "[]",
    },
    {
        "asset_name": "user_accounts.email",
        "table_name": "users",
        "column_names": '["email", "phone"]',
        "pii_category": "contact",
        "lawful_basis": "consent",
        "retention_policy": "Until account deletion + 90 days",
        "storage_location": "ap-south-1 RDS, encrypted at rest",
        "shared_with": "[]",
    },
]


async def seed_data_register(db: AsyncSession) -> int:
    """Seed the DPDP data register with all known PII assets.

    Idempotent — skips assets that already exist.

    Returns the number of new assets inserted.
    """
    count = 0
    for asset_data in SEED_ASSETS:
        existing = await db.execute(
            select(DataAsset).filter(
                DataAsset.asset_name == asset_data["asset_name"]
            )
        )
        if existing.scalars().first():
            continue

        asset = DataAsset(
            asset_name=asset_data["asset_name"],
            table_name=asset_data["table_name"],
            column_names=asset_data["column_names"],
            pii_category=asset_data["pii_category"],
            lawful_basis=asset_data["lawful_basis"],
            retention_policy=asset_data["retention_policy"],
            storage_location=asset_data["storage_location"],
            shared_with=asset_data.get("shared_with", "[]"),
            last_reviewed=datetime.now(timezone.utc),
        )
        db.add(asset)
        count += 1

    if count > 0:
        await db.flush()
        logger.info("Seeded %d DPDP data assets", count)

    return count


async def build_register(db: AsyncSession) -> List[DataAsset]:
    """Retrieve the full DPDP data register."""
    result = await db.execute(
        select(DataAsset).order_by(DataAsset.table_name, DataAsset.asset_name)
    )
    return list(result.scalars().all())


async def export_register_json(db: AsyncSession) -> str:
    """Export the DPDP register as a JSON string."""
    assets = await build_register(db)
    data = []
    for a in assets:
        data.append({
            "asset_name": a.asset_name,
            "table_name": a.table_name,
            "columns": json.loads(a.column_names),
            "pii_category": a.pii_category,
            "lawful_basis": a.lawful_basis,
            "retention_policy": a.retention_policy,
            "storage_location": a.storage_location,
            "shared_with": json.loads(a.shared_with) if a.shared_with else [],
            "last_reviewed": a.last_reviewed.isoformat() if a.last_reviewed else None,
        })
    return json.dumps({"register": data, "generated_at": datetime.now(timezone.utc).isoformat()}, indent=2)