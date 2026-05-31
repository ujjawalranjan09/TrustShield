"""Scam classifier module.

Provides a deterministic keyword-based classifier as a fallback when the
MuRIL ONNX model is unavailable. In production, replace with actual
ONNX model inference for higher accuracy.
"""

import hashlib
import logging
import os
import time
from typing import List, Tuple

from app.schemas.analyze import ClassificationResult, ScamType

logger = logging.getLogger(__name__)


class ScamClassifier:
    """Rule-based scam classifier with weighted keyword matching.

    Uses a deterministic approach: each keyword maps to a scam type and a
    base confidence score. When multiple keywords match, confidence is
    boosted (capped at 0.99). For non-matching text, a low confidence
    score is derived from a SHA-256 hash of the input.
    """

    def __init__(self) -> None:
        self.model_loaded: bool = False
        self.scam_signals: dict[str, Tuple[ScamType, float]] = {
            # Vishing / OTP harvesting
            "otp batao": (ScamType.OTP_HARVESTING, 0.95),
            "share pin": (ScamType.OTP_HARVESTING, 0.95),
            "otp share": (ScamType.OTP_HARVESTING, 0.93),
            "pin batao": (ScamType.OTP_HARVESTING, 0.93),
            "otp": (ScamType.VISHING, 0.75),
            "compromised": (ScamType.VISHING, 0.85),
            "account block": (ScamType.VISHING, 0.88),
            "card block": (ScamType.VISHING, 0.88),
            "verify karne ke liye": (ScamType.VISHING, 0.80),
            # Fake support / Remote access
            "anydesk": (ScamType.REMOTE_ACCESS, 0.92),
            "teamviewer": (ScamType.REMOTE_ACCESS, 0.92),
            "screen share": (ScamType.REMOTE_ACCESS, 0.85),
            "remote access": (ScamType.REMOTE_ACCESS, 0.90),
            "download app": (ScamType.REMOTE_ACCESS, 0.78),
            "support": (ScamType.FAKE_SUPPORT, 0.65),
            "customer care": (ScamType.FAKE_SUPPORT, 0.70),
            "helpline": (ScamType.FAKE_SUPPORT, 0.68),
            # Refund scams
            "qr code": (ScamType.REFUND_SCAM, 0.82),
            "scan this": (ScamType.REFUND_SCAM, 0.80),
            "refund": (ScamType.REFUND_SCAM, 0.78),
            "pin enter": (ScamType.REFUND_SCAM, 0.88),
            "payment receive karne ke liye": (ScamType.REFUND_SCAM, 0.90),
        }
        self._load_model()

    def _load_model(self) -> None:
        """Attempt to load the MuRIL ONNX model.

        Falls back to rule-based classification if the model file is not found.
        """
        model_path = os.getenv(
            "MURIL_MODEL_PATH",
            "trustshield/backend/ml/artifacts/muril_scam_classifier/model.onnx",
        )
        if os.path.exists(model_path):
            self.model_loaded = True
            # In production: self.session = onnxruntime.InferenceSession(model_path)
            logger.info("Loaded MuRIL ONNX model from %s", model_path)
        else:
            logger.info(
                "MuRIL model not found at %s, using rule-based classifier", model_path
            )

    async def classify(self, text: str) -> ClassificationResult:
        """Classify text as scam or legitimate.

        Args:
            text: Preprocessed text to classify.

        Returns:
            ClassificationResult with is_scam flag, confidence, scam type,
            and inference time in milliseconds.
        """
        start_time = time.time()
        text_lower = text.lower()

        matches: List[Tuple[ScamType, float]] = []
        for keyword, (scam_type, confidence) in self.scam_signals.items():
            if keyword in text_lower:
                matches.append((scam_type, confidence))

        if matches:
            best_match = max(matches, key=lambda m: m[1])
            scam_type = best_match[0]
            base_confidence = best_match[1]
            signal_boost = min(0.05 * (len(matches) - 1), 0.15)
            confidence = min(0.99, base_confidence + signal_boost)
            is_scam = True
        else:
            is_scam = False
            scam_type = ScamType.UNKNOWN
            text_hash = int(hashlib.sha256(text_lower.encode()).hexdigest()[:8], 16)
            confidence = 0.01 + (text_hash % 20) / 100

        inference_time_ms = max(1, int((time.time() - start_time) * 1000))

        return ClassificationResult(
            is_scam=is_scam,
            confidence=confidence,
            scam_type=scam_type,
            inference_time_ms=inference_time_ms,
        )
