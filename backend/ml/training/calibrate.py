"""Probability calibration via isotonic regression.

Fits a calibrator on validation-set predictions to ensure the model's
``confidence`` scores are real probabilities.  The calibrator is stored
alongside the model artifacts and applied at inference time.
"""

import json
import logging
import os
import sys
from pathlib import Path
from typing import List, Optional

import numpy as np

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Calibrator
# ---------------------------------------------------------------------------


class IsotonicCalibrator:
    """Per-class isotonic regression calibrator.

    Fits one isotonic regressor per class (one-vs-rest).  The calibrator
    maps uncalibrated probabilities [0, 1] → calibrated probabilities [0, 1].
    """

    def __init__(self):
        self._calibrators: List[Optional[object]] = []
        self._classes: List[int] = []
        self._fitted = False

    def fit(self, probas: np.ndarray, y_true: np.ndarray) -> None:
        """Fit isotonic calibrators.

        Args:
            probas: Shape (n_samples, n_classes) — softmax probabilities.
            y_true: Shape (n_samples,) — integer class labels.
        """
        from sklearn.isotonic import IsotonicRegression

        n_classes = probas.shape[1]
        self._classes = list(range(n_classes))
        self._calibrators = []

        for i in range(n_classes):
            # One-vs-rest: treat class i as positive, all others as negative
            y_binary = (y_true == i).astype(np.float64)
            try:
                calibrator = IsotonicRegression(out_of_bounds="clip")
                calibrator.fit(probas[:, i], y_binary)
                self._calibrators.append(calibrator)
            except Exception as exc:
                logger.warning(
                    "Isotonic regression failed for class %d: %s. "
                    "Falling back to identity.",
                    i,
                    exc,
                )
                # Identity fallback
                identity = IsotonicRegression(out_of_bounds="clip")
                identity.fit(np.array([0.0, 1.0]), np.array([0.0, 1.0]))
                self._calibrators.append(identity)

        self._fitted = True
        logger.info("Fitted %d isotonic calibrators", n_classes)

    def predict(self, probas: np.ndarray) -> np.ndarray:
        """Apply calibration.

        Args:
            probas: Shape (n_samples, n_classes) — softmax probabilities.

        Returns:
            Calibrated probabilities of the same shape.
        """
        if not self._fitted:
            return probas

        calibrated = np.zeros_like(probas)
        for i, cal in enumerate(self._calibrators):
            calibrated[:, i] = cal.predict(probas[:, i])

        # Renormalize to sum to 1
        row_sums = calibrated.sum(axis=1, keepdims=True)
        # Avoid division by zero
        row_sums = np.where(row_sums == 0, 1.0, row_sums)
        calibrated = calibrated / row_sums

        return calibrated

    def save(self, path: str) -> None:
        """Save calibrator to disk."""
        import joblib

        os.makedirs(os.path.dirname(path), exist_ok=True)
        joblib.dump(
            {
                "calibrators": self._calibrators,
                "classes": self._classes,
                "fitted": self._fitted,
            },
            path,
        )
        logger.info("Calibrator saved to %s", path)

    @classmethod
    def load(cls, path: str) -> "IsotonicCalibrator":
        """Load calibrator from disk."""
        import joblib

        data = joblib.load(path)
        instance = cls()
        instance._calibrators = data["calibrators"]
        instance._classes = data["classes"]
        instance._fitted = data["fitted"]
        logger.info("Calibrator loaded from %s", path)
        return instance


# ---------------------------------------------------------------------------
# Calibration evaluation
# ---------------------------------------------------------------------------


def reliability_metrics(
    probas: np.ndarray, y_true: np.ndarray, n_bins: int = 10
) -> dict:
    """Compute reliability (calibration) metrics.

    Returns:
        dict with 'ece' (expected calibration error) and per-bin data.
    """
    if probas.ndim == 1:
        probas = probas.reshape(-1, 1)

    n_classes = probas.shape[1]
    all_ece = 0.0
    bin_data = []

    for i in range(n_classes):
        y_binary = (y_true == i).astype(np.float64)
        confidence = probas[:, i]

        # Bin the predictions
        bin_boundaries = np.linspace(0, 1, n_bins + 1)
        ece = 0.0
        count = 0

        for bin_idx in range(n_bins):
            in_bin = (confidence > bin_boundaries[bin_idx]) & (
                confidence <= bin_boundaries[bin_idx + 1]
            )
            bin_size = in_bin.sum()
            if bin_size == 0:
                continue

            bin_conf = confidence[in_bin].mean()
            bin_acc = y_binary[in_bin].mean()
            gap = abs(bin_conf - bin_acc)
            ece += gap * (bin_size / len(confidence))
            count += 1

            bin_data.append(
                {
                    "class": i,
                    "bin_start": round(bin_boundaries[bin_idx], 2),
                    "bin_end": round(bin_boundaries[bin_idx + 1], 2),
                    "size": int(bin_size),
                    "accuracy": round(bin_acc, 4),
                    "confidence": round(bin_conf, 4),
                    "gap": round(gap, 4),
                }
            )

        all_ece += ece / n_classes

    return {
        "ece": round(all_ece, 4),
        "bins": bin_data,
    }


def calibrate_pipeline(
    probas_path: str, labels_path: str, output_path: str
) -> dict:
    """Full calibration pipeline: load predictions → fit → eval → save.

    Args:
        probas_path: Path to .npy file with shape (n, n_classes) probabilities.
        labels_path: Path to .npy file with shape (n,) integer labels.
        output_path: Where to save the calibrator .pkl file.

    Returns:
        Metrics dict with pre- and post-calibration ECE.
    """
    probas = np.load(probas_path)
    labels = np.load(labels_path)

    # Pre-calibration ECE
    pre_metrics = reliability_metrics(probas, labels)
    logger.info("Pre-calibration ECE: %.4f", pre_metrics["ece"])

    # Fit calibrator
    calibrator = IsotonicCalibrator()
    calibrator.fit(probas, labels)

    # Post-calibration ECE
    calibrated = calibrator.predict(probas)
    post_metrics = reliability_metrics(calibrated, labels)
    logger.info("Post-calibration ECE: %.4f", post_metrics["ece"])

    # Save
    calibrator.save(output_path)

    return {
        "pre_ece": pre_metrics["ece"],
        "post_ece": post_metrics["ece"],
        "improvement": round(pre_metrics["ece"] - post_metrics["ece"], 4),
        "n_samples": len(labels),
        "n_classes": probas.shape[1],
    }


if __name__ == "__main__":
    import argparse

    logging.basicConfig(level=logging.INFO)

    parser = argparse.ArgumentParser(
        description="Fit isotonic calibrator on validation-set predictions"
    )
    parser.add_argument(
        "--probas",
        default="ml/artifacts/val_probas.npy",
        help="Path to validation probabilities .npy",
    )
    parser.add_argument(
        "--labels",
        default="ml/artifacts/val_labels.npy",
        help="Path to validation labels .npy",
    )
    parser.add_argument(
        "--output",
        default="ml/artifacts/calibration.pkl",
        help="Output path for calibrator .pkl",
    )
    args = parser.parse_args()

    base = Path(__file__).resolve().parents[2]
    metrics = calibrate_pipeline(
        str(base / args.probas),
        str(base / args.labels),
        str(base / args.output),
    )
    print(json.dumps(metrics, indent=2))