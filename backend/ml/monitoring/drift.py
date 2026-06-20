"""Population Stability Index (PSI) drift detection.

Computes PSI between baseline and current feature/prediction distributions.
Alerts when PSI > 0.2 (significant drift).

Worker-driven: never called on the hot path.
"""

import logging
from typing import Dict, List

import numpy as np

logger = logging.getLogger(__name__)

PSI_THRESHOLD = 0.2


def compute_psi(baseline: np.ndarray, current: np.ndarray, n_bins: int = 10) -> float:
    """Compute Population Stability Index between two distributions.

    Args:
        baseline: Reference distribution (e.g., training feature values).
        current: New distribution (e.g., recent inference values).
        n_bins: Number of bins for histogram.

    Returns:
        PSI value. >0.2 = significant drift.
    """
    baseline = np.asarray(baseline, dtype=np.float64).flatten()
    current = np.asarray(current, dtype=np.float64).flatten()

    if len(baseline) == 0 or len(current) == 0:
        return 0.0

    # Create bins from combined range
    combined = np.concatenate([baseline, current])
    bins = np.linspace(combined.min(), combined.max(), n_bins + 1)

    # Histograms
    baseline_hist, _ = np.histogram(baseline, bins=bins)
    current_hist, _ = np.histogram(current, bins=bins)

    # Normalize to proportions (avoid zeros)
    baseline_pct = (baseline_hist + 1) / (baseline_hist.sum() + n_bins)
    current_pct = (current_hist + 1) / (current_hist.sum() + n_bins)

    # PSI formula
    psi = np.sum((current_pct - baseline_pct) * np.log(current_pct / baseline_pct))
    return float(psi)


def compute_prediction_drift(
    baseline_probs: np.ndarray,
    current_probs: np.ndarray,
) -> float:
    """Compute PSI on prediction probability distributions."""
    return compute_psi(baseline_probs, current_probs, n_bins=15)


def compute_feature_drift(
    baseline_features: np.ndarray,
    current_features: np.ndarray,
    feature_names: List[str],
) -> Dict[str, float]:
    """Compute PSI per feature."""
    results = {}
    for i, name in enumerate(feature_names):
        if i < baseline_features.shape[1] and i < current_features.shape[1]:
            psi = compute_psi(baseline_features[:, i], current_features[:, i])
            results[name] = round(psi, 6)
    return results


def check_drift_alerts(psi_values: Dict[str, float]) -> List[Dict]:
    """Return alerts for features exceeding PSI threshold."""
    alerts = []
    for feature, psi in psi_values.items():
        if psi > PSI_THRESHOLD:
            alerts.append({
                "feature": feature,
                "psi_value": round(psi, 4),
                "severity": "critical" if psi > 0.25 else "warning",
                "message": f"Drift detected in '{feature}': PSI={psi:.4f} > {PSI_THRESHOLD}",
            })
    return alerts
