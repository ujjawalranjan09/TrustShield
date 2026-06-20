"""Nightly drift monitoring job.

Computes PSI (Population Stability Index) between the training-set
baseline and the last 7 days of model predictions.  Writes results to
``drift_log`` and surfaces on the Explainability dashboard.
"""

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select

from app.config import settings
from app.models.drift import DriftLog
from app.models.scan_event import ScanEvent

logger = logging.getLogger(__name__)


async def run_drift_monitoring() -> dict:
    """Nightly drift job: compute PSI on model_confidence distribution.

    Returns a dict of per-feature drift metrics.
    """
    from app.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        # 1. Get recent predictions (last 7 days)
        cutoff = datetime.now(timezone.utc) - timedelta(days=7)
        recent_result = await db.execute(
            select(ScanEvent.model_confidence)
            .filter(
                ScanEvent.model_confidence.isnot(None),
                ScanEvent.created_at >= cutoff,
            )
            .order_by(ScanEvent.created_at.desc())
        )
        recent_confs = [
            float(r) for r in recent_result.scalars().all() if r is not None
        ]

        if len(recent_confs) < 10:
            logger.info(
                "Not enough recent predictions (%d < 10) to compute drift",
                len(recent_confs),
            )
            return {"status": "skipped", "reason": "insufficient_data", "n_samples": len(recent_confs)}

        # 2. Load the stored baseline distribution from drift_log
        # Use the last computed drift_log as our reference distribution
        baseline_result = await db.execute(
            select(DriftLog)
            .filter(DriftLog.feature_name == "model_confidence")
            .order_by(DriftLog.created_at.desc())
            .limit(1)
        )
        last_log = baseline_result.scalars().first()

        # If we have a previous log, compare. Otherwise this is the first run.
        if last_log and last_log.reference_distribution:
            baseline_confs = last_log.reference_distribution.get("values", [])
        else:
            # First run: just persist the current distribution as baseline
            await _persist_drift_log(db, "model_confidence", recent_confs, recent_confs, 0.0)
            await db.commit()
            return {"status": "baseline_established", "n_samples": len(recent_confs)}

        # 3. Compute PSI — compute_prediction_drift returns a float
        from ml.monitoring.drift import compute_prediction_drift

        psi_value = compute_prediction_drift(
            baseline_confs,
            recent_confs,
        )

        # 4. Log the drift result
        await _persist_drift_log(
            db,
            "model_confidence",
            recent_confs,
            baseline_confs,
            psi_value,
        )
        await db.commit()

        result = {
            "status": "completed",
            "feature": "model_confidence",
            "psi": round(psi_value, 4),
            "n_recent": len(recent_confs),
            "n_baseline": len(baseline_confs),
            "drift_detected": psi_value > 0.2,
        }

        if psi_value > 0.2:
            logger.warning(
                "Drift detected on model_confidence: PSI=%.4f (threshold=0.2)",
                psi_value,
            )
            # Fire alert (placeholder — wire to real alerting)
            try:
                from app.services.alerting.alert_service import trigger_alert

                await trigger_alert(
                    session_id="drift-monitor",
                    risk_score=int(psi_value * 100),
                    risk_level="warning",
                    action="drift_detected",
                    entities=["model_confidence"],
                )
            except Exception:
                logger.info("Alerting not configured — drift warning logged only")

        logger.info("Drift monitoring: PSI=%.4f", psi_value)
        return result


async def _persist_drift_log(
    db,
    feature_name: str,
    recent_values: list,
    baseline_values: list,
    psi: float,
) -> None:
    """Write a DriftLog row."""
    import json

    # Create histogram bins for the reference distribution
    ref_dist = {
        "values": baseline_values,
        "n": len(baseline_values),
        "mean": sum(baseline_values) / len(baseline_values) if baseline_values else 0.0,
        "min": min(baseline_values) if baseline_values else 0.0,
        "max": max(baseline_values) if baseline_values else 0.0,
    }

    log = DriftLog(
        model_version=settings.model_version or "unknown",
        feature_name=feature_name,
        psi_value=psi,
        alert_triggered=psi > 0.2,
        reference_distribution=ref_dist,
        run_id=datetime.now(timezone.utc).isoformat(),
        created_at=datetime.now(timezone.utc),
    )
    db.add(log)


async def compute_and_log_psi(
    baseline_probs_path: str, recent_probs: list, db_session
) -> dict:
    """Compute PSI between baseline .npy file and recent predictions.

    Used by the training pipeline at artifact-export time.
    """
    import numpy as np

    try:
        baseline_probs = np.load(baseline_probs_path).flatten().tolist()
    except Exception as exc:
        logger.warning("Failed to load baseline probs: %s", exc)
        return {"psi": 0.0, "status": "baseline_not_found"}

    if not recent_probs or len(recent_probs) < 10:
        return {"psi": 0.0, "status": "insufficient_data"}

    from ml.monitoring.drift import compute_prediction_drift

    psi_value = compute_prediction_drift(
        baseline_probs,
        recent_probs,
    )
    return {"psi": round(psi_value, 4), "status": "completed", "drift_detected": psi_value > 0.2}