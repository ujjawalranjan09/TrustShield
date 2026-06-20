"""Threat-intelligence ingest — consumes public blocklists.

Idempotent: re-ingesting the same blocklist does not inflate report_count.
Sources: RBI advisories, CERT-In, custom CSV/JSON blocklists.
"""

import asyncio
import hashlib
import json
import logging
import os
from typing import Any, Dict, List

from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)

BLOCKLIST_DIR = os.getenv("THREAT_INTEL_DIR", "ml/data/threat_intel")


def _hash_entity(value: str) -> str:
    return hashlib.sha256(value.lower().strip().encode()).hexdigest()[:32]


async def _ingest_threat_intel() -> Dict[str, Any]:
    """Ingest blocklists from the threat_intel directory."""

    if not os.path.exists(BLOCKLIST_DIR):
        os.makedirs(BLOCKLIST_DIR, exist_ok=True)
        logger.info("Created threat_intel directory: %s", BLOCKLIST_DIR)
        return {"status": "no_data", "ingested": 0}

    total_ingested = 0
    sources_processed = 0

    for filename in os.listdir(BLOCKLIST_DIR):
        filepath = os.path.join(BLOCKLIST_DIR, filename)
        if not (filename.endswith(".json") or filename.endswith(".csv")):
            continue

        try:
            entries = _load_blocklist(filepath)
            count = await _ingest_entries(entries, filename)
            total_ingested += count
            sources_processed += 1
            logger.info("Ingested %d entries from %s", count, filename)
        except Exception as e:
            logger.error("Failed to ingest %s: %s", filename, e)

    return {
        "status": "success",
        "sources_processed": sources_processed,
        "ingested": total_ingested,
    }


def _load_blocklist(filepath: str) -> List[Dict]:
    """Load entries from JSON or CSV blocklist."""
    if filepath.endswith(".json"):
        with open(filepath, encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            return data
        return data.get("entries", [])

    # CSV format: value,type,scam_type,source
    entries = []
    with open(filepath, encoding="utf-8") as f:
        f.readline()  # skip header
        for line in f:
            parts = line.strip().split(",")
            if len(parts) >= 2:
                entries.append({
                    "value": parts[0].strip(),
                    "type": parts[1].strip() if len(parts) > 1 else "PHONE",
                    "scam_type": parts[2].strip() if len(parts) > 2 else "unknown",
                })
    return entries


async def _ingest_entries(entries: List[Dict], source: str) -> int:
    """Idempotent upsert of blocklist entries."""
    from sqlalchemy import select
    from app.database import AsyncSessionLocal
    from app.models.entity import FlaggedEntity

    ingested = 0
    async with AsyncSessionLocal() as db:
        for entry in entries:
            value = entry.get("value", "").strip()
            if not value:
                continue

            entity_key = f"{entry.get('type', 'PHONE')}:{value.lower()}"
            existing = await db.execute(
                select(FlaggedEntity).filter(FlaggedEntity.entity_value == entity_key)
            )
            if existing.scalars().first():
                continue

            entity = FlaggedEntity(
                entity_value=entity_key,
                entity_type=entry.get("type", "PHONE"),
                scam_type=entry.get("scam_type", "unknown"),
                description=f"Threat-intel ingest from {source}",
                report_count=1,
                is_confirmed=1,  # threat-intel entries are pre-confirmed
                source="threat_intel",
            )
            db.add(entity)
            ingested += 1

        await db.commit()
    return ingested


@celery_app.task(name="app.services.intel.threat_ingest.ingest_threat_intel")
def ingest_threat_intel() -> Dict[str, Any]:
    """Celery task for daily threat-intel ingest."""
    return asyncio.run(_ingest_threat_intel())


if __name__ == "__main__":
    ingest_threat_intel()
