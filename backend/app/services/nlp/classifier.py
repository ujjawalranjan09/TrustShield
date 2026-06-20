"""Scam classifier with ONNX inference + fallback chain.

Priority:
1. Transformer ONNX model (highest accuracy)
2. GBM ONNX model (feature-based)
3. Keyword rules (deterministic fallback)
"""

import asyncio
import hashlib
import logging
import time
from typing import List, Optional, Tuple

import numpy as np

from app.schemas.analyze import ClassificationResult, ScamType

logger = logging.getLogger(__name__)

LABEL_MAP = {
    0: ScamType.UNKNOWN,
    1: ScamType.OTP_HARVESTING,
    2: ScamType.VISHING,
    3: ScamType.REMOTE_ACCESS,
    4: ScamType.REFUND_SCAM,
    5: ScamType.FAKE_SUPPORT,
    6: ScamType.PHISHING,
    7: ScamType.SIM_SWAP,
}

SCAM_KEYWORDS = {
    "otp batao": (ScamType.OTP_HARVESTING, 0.95),
    "share pin": (ScamType.OTP_HARVESTING, 0.95),
    "otp share": (ScamType.OTP_HARVESTING, 0.93),
    "pin batao": (ScamType.OTP_HARVESTING, 0.93),
    "otp": (ScamType.VISHING, 0.75),
    "compromised": (ScamType.VISHING, 0.85),
    "account block": (ScamType.VISHING, 0.88),
    "card block": (ScamType.VISHING, 0.88),
    "verify karne ke liye": (ScamType.VISHING, 0.80),
    "anydesk": (ScamType.REMOTE_ACCESS, 0.92),
    "teamviewer": (ScamType.REMOTE_ACCESS, 0.92),
    "screen share": (ScamType.REMOTE_ACCESS, 0.85),
    "remote access": (ScamType.REMOTE_ACCESS, 0.90),
    "download app": (ScamType.REMOTE_ACCESS, 0.78),
    "support": (ScamType.FAKE_SUPPORT, 0.65),
    "customer care": (ScamType.FAKE_SUPPORT, 0.70),
    "helpline": (ScamType.FAKE_SUPPORT, 0.68),
    "qr code": (ScamType.REFUND_SCAM, 0.82),
    "scan this": (ScamType.REFUND_SCAM, 0.80),
    "refund": (ScamType.REFUND_SCAM, 0.78),
    "pin enter": (ScamType.REFUND_SCAM, 0.88),
    "payment receive karne ke liye": (ScamType.REFUND_SCAM, 0.90),
    "click this link": (ScamType.PHISHING, 0.88),
    "verify your account": (ScamType.PHISHING, 0.85),
    "sim": (ScamType.SIM_SWAP, 0.70),
    "sim swap": (ScamType.SIM_SWAP, 0.90),
    # Hindi patterns
    "otp bhejo": (ScamType.OTP_HARVESTING, 0.95),
    "otp bhej do": (ScamType.OTP_HARVESTING, 0.95),
    "otp forward": (ScamType.OTP_HARVESTING, 0.93),
    "pin bhejo": (ScamType.OTP_HARVESTING, 0.93),
    "code batao": (ScamType.OTP_HARVESTING, 0.90),
    "account band": (ScamType.VISHING, 0.88),
    "card band": (ScamType.VISHING, 0.88),
    "kyc update": (ScamType.VISHING, 0.85),
    "bank se call": (ScamType.VISHING, 0.82),
    "suspicious activity": (ScamType.VISHING, 0.85),
    "turant": (ScamType.VISHING, 0.60),
    "jaldi": (ScamType.VISHING, 0.55),
    "anydesk download": (ScamType.REMOTE_ACCESS, 0.92),
    "screen dikhao": (ScamType.REMOTE_ACCESS, 0.85),
    "qr scan": (ScamType.REFUND_SCAM, 0.82),
    "paisa milega": (ScamType.REFUND_SCAM, 0.80),
    "refund milega": (ScamType.REFUND_SCAM, 0.78),
}


class ScamClassifier:
    """Multi-tier scam classifier with ONNX models + keyword fallback.

    Priority:
    1. Transformer ONNX model (with 50ms timeout)
    2. GBM ONNX model (feature-based)
    3. Keyword rules (deterministic fallback)

    Counts fallback events as a Prometheus counter for observability.
    """

    def __init__(self):
        self._loader = None
        self._keyword_classifier = None
        self._fallback_counter = None

    def _get_loader(self):
        if self._loader is None:
            from app.services.nlp.model_loader import ModelLoader
            self._loader = ModelLoader()
            if not self._loader.transformer_available and not self._loader.gbm_available:
                self._loader.load()
        return self._loader

    def _record_fallback(self, tier: str) -> None:
        """Record a fallback event to Prometheus."""
        try:
            if self._fallback_counter is None:
                from prometheus_client import Counter
                self._fallback_counter = Counter(
                    "model_fallback_total",
                    "Number of model fallback events by tier",
                    ["tier"],
                )
            self._fallback_counter.labels(tier=tier).inc()
        except Exception:
            pass

    async def classify(self, text: str) -> ClassificationResult:
        """Classify text using the best available model."""
        start_time = time.time()

        # Try transformer first (with timeout)
        loader = self._get_loader()
        if loader.transformer_available:
            result = await self._classify_transformer(text, loader)
            if result:
                result.inference_time_ms = max(1, int((time.time() - start_time) * 1000))
                return result

        self._record_fallback("transformer")

        # Try GBM
        if loader.gbm_available:
            result = await self._classify_gbm(text, loader)
            if result:
                result.inference_time_ms = max(1, int((time.time() - start_time) * 1000))
                return result

        self._record_fallback("gbm")

        # Fallback to keywords
        result = self._classify_keywords(text)
        result.inference_time_ms = max(1, int((time.time() - start_time) * 1000))
        return result

    def _apply_calibrator(self, probs: np.ndarray, loader) -> np.ndarray:
        """Apply the calibrator if available."""
        try:
            if loader.calibrator is not None:
                return loader.calibrator.predict(probs.reshape(1, -1)).flatten()
        except Exception as exc:
            logger.warning("Calibrator application failed: %s", exc)
        return probs

    async def _classify_transformer(self, text: str, loader) -> ClassificationResult | None:
        """Classify using transformer ONNX model with 50ms timeout."""
        try:
            if loader.tokenizer is None:
                return None

            # Tokenize
            if hasattr(loader.tokenizer, "encode"):
                encoding = loader.tokenizer.encode(text)
                input_ids = np.array([encoding.ids], dtype=np.int64)
                attention_mask = np.array([encoding.attention_mask], dtype=np.int64)
            else:
                encoding = loader.tokenizer(
                    text, truncation=True, padding=True,
                    max_length=256, return_tensors="np"
                )
                input_ids = encoding["input_ids"]
                attention_mask = encoding["attention_mask"]

            # Run inference with 50ms timeout via a thread
            outputs = await asyncio.wait_for(
                asyncio.to_thread(
                    loader.predict_transformer, input_ids, attention_mask
                ),
                timeout=0.05,
            )
            logits = outputs[0][0]

            # Softmax
            exp_logits = np.exp(logits - np.max(logits))
            probs = exp_logits / exp_logits.sum()

            # Apply calibrator
            probs = self._apply_calibrator(probs, loader)

            predicted_class = int(np.argmax(probs))
            confidence = float(probs[predicted_class])

            scam_type = LABEL_MAP.get(predicted_class, ScamType.UNKNOWN)
            is_scam = predicted_class != 0

            return ClassificationResult(
                is_scam=is_scam,
                confidence=round(confidence, 4),
                scam_type=scam_type,
                inference_time_ms=0,
            )
        except asyncio.TimeoutError:
            logger.warning("Transformer inference timed out (>50ms)")
            self._record_fallback("transformer_timeout")
            return None
        except Exception as exc:
            logger.warning("Transformer classification failed: %s", exc)
            return None

    async def _classify_gbm(self, text: str, loader) -> ClassificationResult | None:
        """Classify using GBM ONNX model."""
        try:
            from ml.training.features import extract_features, get_feature_names

            # Simulate a single-message conversation for feature extraction
            messages = [{"sender": "unknown", "text": text}]
            features = extract_features(messages)
            feature_names = get_feature_names()
            feature_vector = np.array([[features.get(name, 0.0) for name in feature_names]], dtype=np.float32)

            outputs = await asyncio.wait_for(
                asyncio.to_thread(loader.predict_gbm, feature_vector),
                timeout=0.02,
            )
            logits = outputs[0][0]

            exp_logits = np.exp(logits - np.max(logits))
            probs = exp_logits / exp_logits.sum()

            # Apply calibrator
            probs = self._apply_calibrator(probs, loader)

            predicted_class = int(np.argmax(probs))
            confidence = float(probs[predicted_class])

            scam_type = LABEL_MAP.get(predicted_class, ScamType.UNKNOWN)
            is_scam = predicted_class != 0

            return ClassificationResult(
                is_scam=is_scam,
                confidence=round(confidence, 4),
                scam_type=scam_type,
                inference_time_ms=0,
            )
        except asyncio.TimeoutError:
            logger.warning("GBM inference timed out (>20ms)")
            return None
        except Exception as exc:
            logger.warning("GBM classification failed: %s", exc)
            return None

    def _classify_keywords(self, text: str) -> ClassificationResult:
        """Keyword-based fallback classifier."""
        text_lower = text.lower()
        matches: List[Tuple[ScamType, float]] = []

        for keyword, (scam_type, confidence) in SCAM_KEYWORDS.items():
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

        return ClassificationResult(
            is_scam=is_scam,
            confidence=confidence,
            scam_type=scam_type,
            inference_time_ms=0,
        )
