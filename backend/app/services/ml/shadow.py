"""Shadow mode — run a candidate model in parallel without affecting production.

Shadow predictions are logged to a ``shadow_predictions`` table for later
comparison.  The promotion worker (``promotion.py``) uses these to decide
if the candidate model is safe to hot-swap.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import func, select

from app.config import settings
from app.models.shadow_prediction import ShadowPrediction

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Shadow Runner
# ---------------------------------------------------------------------------

class ShadowRunner:
    """Runs a candidate model in shadow mode alongside the primary model.

    The shadow result is logged but never returned to the caller.
    """

    def __init__(self, shadow_model_path: str):
        self.shadow_model_path = shadow_model_path
        self._shadow_loader = None
        self._primary_loader = None

    async def run_shadow(
        self,
        text: str,
        session_id: str,
        primary_result: dict,
        db: AsyncSession,
    ) -> Optional[ShadowPrediction]:
        """Run the shadow model and log the comparison.

        Args:
            text: Input text to classify.
            session_id: Session identifier for correlation.
            primary_result: dict with 'prediction' and 'confidence' from the
                            production model.
            db: AsyncSession for persisting the shadow prediction.

        Returns:
            The ShadowPrediction row, or None on failure.
        """
        try:
            from app.services.nlp.classifier import ScamClassifier

            # Run shadow classifier
            classifier = ScamClassifier()
            shadow_result = await classifier.classify(text)

            # Map ClassificationResult to IDs
            shadow_pred = 1 if shadow_result.is_scam else 0
            shadow_conf = shadow_result.confidence

            primary_pred = 1 if primary_result.get("is_scam", False) else 0
            primary_conf = primary_result.get("confidence", 0.0)

            agreement = 1 if shadow_pred == primary_pred else 0

            sp = ShadowPrediction(
                session_id=session_id,
                primary_prediction=primary_pred,
                primary_confidence=primary_conf,
                shadow_prediction=shadow_pred,
                shadow_confidence=shadow_conf,
                shadow_model_version=settings.model_version or "unknown",
                primary_model_version="production",
                agreement=agreement,
            )
            db.add(sp)
            await db.flush()

            logger.debug(
                "Shadow: session=%s primary=%d(%.4f) shadow=%d(%.4f) agree=%d",
                session_id,
                primary_pred,
                primary_conf,
                shadow_pred,
                shadow_conf,
                agreement,
            )

            return sp
        except Exception as exc:
            logger.warning("Shadow prediction failed: %s", exc)
            return None


async def get_shadow_agreement_rate(
    db: AsyncSession,
    window_days: int = 7,
    min_samples: int = 100,
) -> Optional[dict]:
    """Compute the shadow agreement rate over the given window.

    Args:
        db: Database session.
        window_days: Lookback window in days (default 7).
        min_samples: Minimum number of shadow predictions required.

    Returns:
        dict with 'agreement_rate', 'n_samples', 'window_days', or None
        if insufficient samples.
    """

    cutoff = datetime.now(timezone.utc) - timedelta(days=window_days)

    result = await db.execute(
        select(
            func.count().label("total"),
            func.sum(ShadowPrediction.agreement).label("agreements"),
        ).filter(ShadowPrediction.created_at >= cutoff)
    )
    row = result.one()
    total = row.total or 0

    if total < min_samples:
        return None

    agreements = row.agreements or 0
    return {
        "agreement_rate": round(agreements / total, 4),
        "n_samples": total,
        "window_days": window_days,
    }