"""Tests for isotonic calibration layer."""

import numpy as np
import pytest

from ml.training.calibrate import IsotonicCalibrator, reliability_metrics


class TestIsotonicCalibrator:
    def test_fit_and_predict(self):
        """Calibrator should fit and return calibrated probabilities."""
        n_samples = 100
        n_classes = 4

        # Generate synthetic probabilities and labels
        np.random.seed(42)
        probas = np.random.dirichlet(np.ones(n_classes), n_samples)
        labels = np.random.randint(0, n_classes, n_samples)

        calibrator = IsotonicCalibrator()
        calibrator.fit(probas, labels)

        calibrated = calibrator.predict(probas)

        assert calibrated.shape == (n_samples, n_classes)
        # Should sum to 1 per row
        assert np.allclose(calibrated.sum(axis=1), 1.0, atol=1e-5)

    def test_save_and_load(self, tmp_path):
        """Calibrator should round-trip through save/load."""
        n_samples = 50
        n_classes = 3
        np.random.seed(42)
        probas = np.random.dirichlet(np.ones(n_classes), n_samples)
        labels = np.random.randint(0, n_classes, n_samples)

        calibrator = IsotonicCalibrator()
        calibrator.fit(probas, labels)

        save_path = tmp_path / "calibration.pkl"
        calibrator.save(str(save_path))

        loaded = IsotonicCalibrator.load(str(save_path))
        assert loaded._fitted
        assert len(loaded._calibrators) == n_classes

    def test_not_fitted_identity(self):
        """Unfitted calibrator should return input unchanged."""
        probas = np.array([[0.7, 0.3], [0.2, 0.8]])
        calibrator = IsotonicCalibrator()

        result = calibrator.predict(probas)
        assert np.allclose(result, probas)

    def test_reliability_metrics(self):
        """reliability_metrics should return ECE and bins."""
        probas = np.array([[0.9, 0.1], [0.8, 0.2], [0.3, 0.7], [0.1, 0.9]])
        labels = np.array([0, 0, 1, 1])

        metrics = reliability_metrics(probas, labels, n_bins=5)
        assert "ece" in metrics
        assert "bins" in metrics
        assert metrics["ece"] >= 0.0