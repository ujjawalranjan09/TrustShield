"""Cell evacuation — migrate all tenants from one region to another.

RTO target: 4 hours for a full cell evacuation.

The evacuation process:
1. Query all tenants in the source region.
2. For each tenant, export data via compliance export_pack.
3. Import data into the target cell.
4. Re-pin tenant.data_region to the target region.
5. Return summary of migration results.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.tenant import Tenant

logger = logging.getLogger(__name__)


async def _get_tenants_in_region(
    region: str, db: AsyncSession
) -> List[Tenant]:
    """Return all tenants pinned to the given region."""
    result = await db.execute(
        select(Tenant).filter(Tenant.data_region == region)
    )
    return list(result.scalars().all())


async def _export_tenant_data(
    tenant_id: str, db: AsyncSession
) -> Dict[str, Any]:
    """Export a single tenant's data via compliance export_pack."""
    from app.services.compliance.export_pack import generate_regulator_pack

    try:
        pack_bytes = await generate_regulator_pack(
            db=db,
            quarter="evacuation",
            signed_by_admin_id=0,
            include_gold_report=False,
        )
        return {"tenant_id": tenant_id, "export_bytes": len(pack_bytes), "success": True}
    except Exception as exc:
        logger.error("Export failed for tenant %s: %s", tenant_id, exc)
        return {"tenant_id": tenant_id, "error": str(exc), "success": False}


async def _import_to_target_cell(
    tenant_id: str,
    pack_bytes: bytes,
    target_region: str,
) -> Dict[str, Any]:
    """Import exported data into the target cell via its API.

    In production this would POST to the target cell's import endpoint.
    Here we return a placeholder — the actual import is cell-specific
    and should be implemented per deployment.
    """
    cell_urls_raw = settings.cell_urls
    if not cell_urls_raw:
        return {"tenant_id": tenant_id, "error": "No cell URLs configured", "success": False}

    try:
        import json
        cell_urls = json.loads(cell_urls_raw)
    except (json.JSONDecodeError, TypeError):
        return {"tenant_id": tenant_id, "error": "Invalid cell_urls config", "success": False}

    target_url = cell_urls.get(target_region)
    if not target_url:
        return {
            "tenant_id": tenant_id,
            "error": f"No URL for target region {target_region}",
            "success": False,
        }

    import httpx

    try:
        async with httpx.AsyncClient(timeout=300, verify=True) as client:
            resp = await client.post(
                f"{target_url.rstrip('/')}/api/v1/compliance/import-pack",
                content=pack_bytes,
                headers={
                    "Content-Type": "application/zip",
                    "X-Evacuation-Import": "true",
                    "X-Source-Region": settings.cell_region,
                },
            )
            if resp.status_code == 200:
                return {"tenant_id": tenant_id, "success": True}
            return {
                "tenant_id": tenant_id,
                "success": False,
                "error": f"Target returned {resp.status_code}",
            }
    except Exception as exc:
        logger.error("Import to %s failed for tenant %s: %s", target_region, tenant_id, exc)
        return {"tenant_id": tenant_id, "success": False, "error": str(exc)}


async def evacuate_cell(
    from_region: str,
    to_region: str,
    db: AsyncSession,
) -> Dict[str, Any]:
    """Evacuate all tenants from one cell region to another.

    Process per tenant:
    1. Export data via compliance export_pack
    2. Import into target cell
    3. Re-pin data_region to target

    RTO target: 4 hours for full cell.
    """
    tenants = await _get_tenants_in_region(from_region, db)
    logger.info(
        "Evacuation initiated: %s -> %s (%d tenants)",
        from_region,
        to_region,
        len(tenants),
    )

    results: List[Dict[str, Any]] = []
    success_count = 0
    errors: List[str] = []

    for tenant in tenants:
        try:
            # Step 1: Export
            export_result = await _export_tenant_data(tenant.tenant_id, db)
            if not export_result.get("success"):
                errors.append(
                    f"Export failed for {tenant.tenant_id}: {export_result.get('error')}"
                )
                results.append(export_result)
                continue

            # Step 2: Import to target cell
            # Re-read export bytes for import
            from app.services.compliance.export_pack import generate_regulator_pack
            pack_bytes = await generate_regulator_pack(
                db=db,
                quarter="evacuation",
                signed_by_admin_id=0,
                include_gold_report=False,
            )
            import_result = await _import_to_target_cell(
                tenant.tenant_id, pack_bytes, to_region
            )
            if not import_result.get("success"):
                errors.append(
                    f"Import failed for {tenant.tenant_id}: {import_result.get('error')}"
                )
                results.append(import_result)
                continue

            # Step 3: Re-pin tenant
            tenant.data_region = to_region
            await db.flush()
            success_count += 1
            results.append({"tenant_id": tenant.tenant_id, "success": True})

        except Exception as exc:
            error_msg = f"Evacuation failed for {tenant.tenant_id}: {exc}"
            logger.error(error_msg)
            errors.append(error_msg)
            results.append({"tenant_id": tenant.tenant_id, "success": False, "error": str(exc)})

    if success_count > 0:
        await db.commit()

    summary = {
        "from_region": from_region,
        "to_region": to_region,
        "tenants_migrated": success_count,
        "total_tenants": len(tenants),
        "success": len(errors) == 0,
        "errors": errors,
    }
    logger.info("Evacuation complete: %s", summary)
    return summary
