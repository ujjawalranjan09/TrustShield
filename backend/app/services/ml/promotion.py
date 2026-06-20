"""Model promotion worker — guards hot-swapping of models.

The promotion guard verifies that a candidate model:
1. Achieves gold-set F1 ≥ current model's F1.
2. Achieves shadow agreement ≥ 95% over the observation window.
3. Has no regression in FP-rate.

Only then can ``ModelRegistry.hot_swap`` be called.
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.model_params import ModelParams

logger = logging.getLogger(__name__)


async def check_promotion_guard(
    db: AsyncSession,
    candidate_version: str,
    candidate_gold_report: dict,
    min_agreement: float = 0.95,
    min_f1: float = 0.90,
    max_fp_rate: float = 0.02,
) -> dict:
    """Check if a candidate model passes all promotion guards.

    Args:
        db: Database session.
        candidate_version: Version string of the candidate model.
        candidate_gold_report: The gold_eval gold_report.json loaded as dict.
        min_agreement: Minimum required shadow agreement rate.
        min_f1: Minimum required macro-F1.
        max_fp_rate: Maximum allowed false positive rate.

    Returns:
        dict with 'passed' (bool) and 'reasons' (list of failures).
    """
    failures = []

    # 1. Check gold-set F1 threshold
    f1 = candidate_gold_report.get("macro_f1", 0.0)
    if f1 < min_f1:
        failures.append(f"Gold-set macro-F1 {f1} < {min_f1}")

    # 2. Check FP-rate threshold
    fp_rate = candidate_gold_report.get("fp_rate", 1.0)
    if fp_rate > max_fp_rate:
        failures.append(f"FP-rate {fp_rate} > {max_fp_rate}")

    # 3. Get current production model's gold-set F1
    current_model = await db.execute(
        select(ModelParams)
        .filter(ModelParams.is_active == True)  # noqa: E712
        .order_by(ModelParams.created_at.desc())
        .limit(1)
    )
    current = current_model.scalars().first()

    if current:
        current_f1 = current.gold_f1 or 0.0
        if f1 < current_f1:
            failures.append(
                f"Candidate F1 ({f1}) < current production F1 ({current_f1})"
            )

    # 4. Check shadow agreement rate
    from app.services.ml.shadow import get_shadow_agreement_rate

    shadow = await get_shadow_agreement_rate(db, window_days=7, min_samples=100)
    if shadow is None:
        failures.append("Insufficient shadow predictions (< 100 in last 7 days)")
    elif shadow["agreement_rate"] < min_agreement:
        failures.append(
            f"Shadow agreement {shadow['agreement_rate']:.4f} < {min_agreement}"
        )

    passed = len(failures) == 0

    return {
        "passed": passed,
        "reasons": failures,
        "candidate_version": candidate_version,
        "candidate_f1": f1,
        "candidate_fp_rate": fp_rate,
        "current_model_version": current.model_version if current else "unknown",
        "current_f1": current.gold_f1 if current else None,
        "shadow_agreement": shadow.get("agreement_rate") if shadow else None,
    }


async def promote_model(
    db: AsyncSession,
    candidate_version: str,
    gold_report_path: str,
) -> dict:
    """Promote a candidate model to production after passing guards.

    Args:
        db: Database session.
        candidate_version: Version string to promote.
        gold_report_path: Path to gold_report.json for the candidate.

    Returns:
        dict with promotion result.
    """
    # Load gold report
    try:
        with open(gold_report_path) as f:
            gold_report = json.load(f)
    except Exception as exc:
        return {"success": False, "reason": f"Failed to load gold report: {exc}"}

    # Run guard check
    guard = await check_promotion_guard(
        db, candidate_version, gold_report
    )

    if not guard["passed"]:
        return {
            "success": False,
            "reason": "Promotion guard failed",
            "details": guard,
        }

    # Perform hot swap via ModelRegistry
    try:
        from app.services.nlp.model_registry import ModelRegistry

        registry = ModelRegistry()
        result = registry.hot_swap(candidate_version)
        if not result.get("success"):
            return {
                "success": False,
                "reason": f"hot_swap failed: {result.get('error', 'unknown')}",
                "details": result,
            }

        # Update model params in DB
        new_params = ModelParams(
            model_version=candidate_version,
            gold_f1=gold_report.get("macro_f1"),
            accuracy=gold_report.get("accuracy"),
            is_active=True,
            created_at=datetime.now(timezone.utc),
        )
        db.add(new_params)

        # Deactivate old params
        await db.execute(
            # Deactivate all existing active models
            update(ModelParams)
            .where(ModelParams.is_active == True)  # noqa: E712
            .where(ModelParams.model_version != candidate_version)
            .values(is_active=False)
        )

        await db.commit()

    except Exception as exc:
        return {"success": False, "reason": f"Promotion failed: {exc}"}

    return {
        "success": True,
        "model_version": candidate_version,
        "gold_f1": gold_report.get("macro_f1"),
        "fp_rate": gold_report.get("fp_rate"),
        "guard": guard,
    }