"""BentoML model serving service for TrustShield scam classifier.

Provides a high-performance inference endpoint for the transformer and
gradient-boosted model ONNX runtimes with calibration.
"""

import logging
import os
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)

try:
    import bentoml
    from bentoml.io import JSON, Text

    BENTOML_AVAILABLE = True
except ImportError:
    BENTOML_AVAILABLE = False
    logger.warning("bentoml not installed; model service disabled")

if BENTOML_AVAILABLE:

    @bentoml.service(
        resources={"cpu": "2"},
        traffic={"timeout": 30},
    )
    class ScamClassifierService:
        """Scam classifier model service with transformer and GBM backends."""

        def __init__(self):
            self._transformer_model = None
            self._gbm_model = None
            self._calibrator = None
            self._artifacts_dir = os.environ.get(
                "MODEL_ARTIFACTS_DIR",
                os.path.join(os.path.dirname(__file__), "artifacts"),
            )
            self._load_models()

        def _load_models(self):
            """Load ONNX models and calibration artifacts."""
            import onnxruntime as ort

            transformer_path = os.path.join(
                self._artifacts_dir, "transformer_model.onnx"
            )
            gbm_path = os.path.join(self._artifacts_dir, "gbm_model.onnx")
            calibrator_path = os.path.join(self._artifacts_dir, "calibration.pkl")

            if os.path.exists(transformer_path):
                self._transformer_model = ort.InferenceSession(transformer_path)
                logger.info("Loaded transformer model from %s", transformer_path)
            else:
                logger.warning("Transformer model not found at %s", transformer_path)

            if os.path.exists(gbm_path):
                self._gbm_model = ort.InferenceSession(gbm_path)
                logger.info("Loaded GBM model from %s", gbm_path)

            if os.path.exists(calibrator_path):
                import pickle

                with open(calibrator_path, "rb") as f:
                    self._calibrator = pickle.load(f)
                logger.info("Loaded calibrator from %s", calibrator_path)

        @bentoml.api(input=Text(), output=JSON())
        def classify_transformer(self, text: str) -> dict:
            """Classify text using the transformer ONNX model."""
            if self._transformer_model is None:
                return {"error": "Transformer model not loaded", "label": "unknown", "confidence": 0.0}

            # Tokenize and run inference
            # Placeholder: actual tokenization depends on the model's tokenizer
            input_ids = np.array([[101] + [0] * 126], dtype=np.int64)
            attention_mask = np.array([[1] + [0] * 126], dtype=np.int64)

            outputs = self._transformer_model.run(
                None,
                {
                    "input_ids": input_ids,
                    "attention_mask": attention_mask,
                },
            )

            logits = outputs[0][0]
            probs = self._softmax(logits)

            if self._calibrator is not None:
                probs = self._calibrator.predict_proba(probs.reshape(1, -1))[0]

            label = "scam" if probs[1] > 0.5 else "legitimate"
            confidence = float(max(probs))

            return {"label": label, "confidence": confidence, "scores": probs.tolist()}

        @bentoml.api(input=JSON(), output=JSON())
        def classify_gbm(self, features: dict) -> dict:
            """Classify using the gradient-boosted model with pre-extracted features."""
            if self._gbm_model is None:
                return {"error": "GBM model not loaded", "label": "unknown", "confidence": 0.0}

            feature_array = np.array(
                [list(features.values())], dtype=np.float32
            )

            outputs = self._gbm_model.run(None, {"features": feature_array})
            logits = outputs[0][0]
            probs = self._softmax(logits)

            label = "scam" if probs[1] > 0.5 else "legitimate"
            confidence = float(max(probs))

            return {"label": label, "confidence": confidence, "scores": probs.tolist()}

        @bentoml.api(input=JSON(), output=JSON())
        def health(self) -> dict:
            """Health check endpoint."""
            return {
                "status": "healthy",
                "transformer_loaded": self._transformer_model is not None,
                "gbm_loaded": self._gbm_model is not None,
                "calibrator_loaded": self._calibrator is not None,
            }

        @staticmethod
        def _softmax(x):
            """Compute softmax values for a logits array."""
            e_x = np.exp(x - np.max(x))
            return e_x / e_x.sum()
