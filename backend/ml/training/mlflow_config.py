"""MLflow experiment tracking configuration."""

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

MLFLOW_TRACKING_URI = os.getenv("MLFLOW_TRACKING_URI", "file:mlruns")
EXPERIMENT_NAME = "trustshield-scam-classifier"


def setup_mlflow():
    """Initialize MLflow tracking."""
    try:
        import mlflow

        mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
        mlflow.set_experiment(EXPERIMENT_NAME)
        logger.info("MLflow tracking URI: %s", MLFLOW_TRACKING_URI)
        return True
    except ImportError:
        logger.warning("mlflow not installed, tracking disabled")
        return False


def log_training_run(
    model_type: str,
    params: dict,
    metrics: dict,
    artifacts_dir: str,
    tags: dict = None,
):
    """Log a training run to MLflow."""
    try:
        import mlflow

        with mlflow.start_run(run_name=f"{model_type}-training"):
            mlflow.log_params(params)
            mlflow.log_metrics(metrics)
            if tags:
                mlflow.set_tags(tags)

            # Log artifacts
            base = Path(artifacts_dir)
            if base.exists():
                mlflow.log_artifacts(str(base))

            run_id = mlflow.active_run().info.run_id
            logger.info("MLflow run logged: %s", run_id)
            return run_id
    except Exception as exc:
        logger.warning("Failed to log to MLflow: %s", exc)
        return None
