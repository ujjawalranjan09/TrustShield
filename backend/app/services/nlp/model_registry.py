"""In-memory model registry — zero hot-path DB reads.

Loads the active model_params row ONCE at startup. Reads are pure
attribute access. Refresh happens on promotion events, never on request path.
"""

import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class ActiveModel:
    model_version: str = "unknown"
    transformer_weight: float = 0.6
    gbm_weight: float = 0.4
    transformer_f1: float = 0.0
    gbm_f1: float = 0.0
    ensemble_f1: float = 0.0
    gold_set_f1: float = 0.0


class ModelRegistry:
    """Singleton that holds the active model config in memory."""

    _instance: Optional["ModelRegistry"] = None
    _active: ActiveModel = field(default_factory=ActiveModel)

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._active = ActiveModel()
        return cls._instance

    @property
    def active(self) -> ActiveModel:
        return self._active

    def load_from_db(self, db_session) -> None:
        """Load the active model_params row. Called once at startup."""
        try:
            from sqlalchemy import select
            from app.models.model_params import ModelParams

            result = db_session.execute(
                select(ModelParams).filter(ModelParams.is_active.is_(True))
            )
            row = result.scalars().first()
            if row:
                self._active = ActiveModel(
                    model_version=row.model_version,
                    transformer_weight=row.transformer_weight,
                    gbm_weight=row.gbm_weight,
                    transformer_f1=row.transformer_f1 or 0.0,
                    gbm_f1=row.gbm_f1 or 0.0,
                    ensemble_f1=row.ensemble_f1 or 0.0,
                    gold_set_f1=row.gold_set_f1 or 0.0,
                )
                logger.info("ModelRegistry loaded active model: %s", row.model_version)
            else:
                logger.info("No active model_params found, using defaults")
        except Exception as exc:
            logger.warning("ModelRegistry failed to load from DB: %s", exc)

    def hot_swap(self, model_version: str, transformer_weight: float = 0.6,
                 gbm_weight: float = 0.4, **metrics) -> None:
        """Atomic swap of the active model. Called by promotion worker."""
        old_version = self._active.model_version
        self._active = ActiveModel(
            model_version=model_version,
            transformer_weight=transformer_weight,
            gbm_weight=gbm_weight,
            **{k: v for k, v in metrics.items() if hasattr(ActiveModel, k)},
        )
        logger.info("ModelRegistry hot-swapped: %s → %s", old_version, model_version)
