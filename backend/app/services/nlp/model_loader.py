"""Singleton ONNX session manager.

Loads transformer + GBM ONNX models at startup. Falls back gracefully
if artifacts are missing. Never re-loads on every request.

Phase C: Adds ``RemoteModelClient`` for calling the BentoML model
service, with ``get_loader()`` factory to select local vs remote.
"""

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

ARTIFACTS_DIR = os.getenv("ML_ARTIFACTS_DIR", "ml/artifacts")


class ModelServiceUnavailable(Exception):
    """Raised when the remote model service is unreachable."""


class RemoteModelClient:
    """HTTP client for the BentoML model service."""

    def __init__(self, base_url: str, timeout_ms: int = 100):
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout_ms / 1000.0
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            timeout=self._timeout,
        )

    async def classify_transformer(self, text: str) -> dict:
        """Classify text via the remote transformer model."""
        try:
            response = await self._client.post(
                "/classify_transformer",
                json={"text": text},
            )
            response.raise_for_status()
            return response.json()
        except httpx.TimeoutException as exc:
            raise ModelServiceUnavailable(
                f"Model service timeout: {exc}"
            ) from exc
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code >= 500:
                raise ModelServiceUnavailable(
                    f"Model service error: {exc.response.status_code}"
                ) from exc
            raise

    async def classify_gbm(self, features: dict) -> dict:
        """Classify via the remote GBM model."""
        try:
            response = await self._client.post(
                "/classify_gbm",
                json=features,
            )
            response.raise_for_status()
            return response.json()
        except httpx.TimeoutException as exc:
            raise ModelServiceUnavailable(
                f"Model service timeout: {exc}"
            ) from exc
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code >= 500:
                raise ModelServiceUnavailable(
                    f"Model service error: {exc.response.status_code}"
                ) from exc
            raise

    def load(self) -> None:
        """No-op for remote client (models loaded server-side)."""

    @property
    def transformer_available(self) -> bool:
        return True

    @property
    def gbm_available(self) -> bool:
        return True

    @property
    def model_version(self) -> str:
        return "remote"


class ModelLoader:
    """Singleton that manages ONNX inference sessions."""

    _instance: Optional["ModelLoader"] = None

    transformer_session: Any = None
    gbm_session: Any = None
    tokenizer: Any = None
    label_map: Dict[int, str] = {}
    feature_names: List[str] = []
    model_version: str = "unknown"
    transformer_available: bool = False
    gbm_available: bool = False
    calibrator: Any = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def load(self, artifacts_dir: str = ARTIFACTS_DIR) -> None:
        """Load all available ONNX models and metadata."""
        base = Path(artifacts_dir)

        # Load transformer
        transformer_dir = base / "transformer"
        onnx_path = transformer_dir / "model.onnx"
        config_path = transformer_dir / "config.json"

        if onnx_path.exists():
            try:
                import onnxruntime as ort
                self.transformer_session = ort.InferenceSession(str(onnx_path))
                self.transformer_available = True
                logger.info("Loaded transformer ONNX from %s", onnx_path)
            except Exception as exc:
                logger.warning("Failed to load transformer ONNX: %s", exc)
        else:
            logger.info("Transformer ONNX not found at %s", onnx_path)

        if config_path.exists():
            with open(config_path) as f:
                config = json.load(f)
            self.label_map = {int(k): v for k, v in config.get("label_map", {}).items()}
            self.model_version = config.get("model_version", "unknown")

        # Load tokenizer (fast Rust tokenizer preferred)
        tokenizer_path = transformer_dir / "tokenizer.json"
        if tokenizer_path.exists():
            try:
                from tokenizers import Tokenizer
                self.tokenizer = Tokenizer.from_file(str(tokenizer_path))
                logger.info("Loaded fast tokenizer from %s", tokenizer_path)
            except ImportError:
                logger.warning("tokenizers package not installed, trying AutoTokenizer")
                try:
                    from transformers import AutoTokenizer
                    self.tokenizer = AutoTokenizer.from_pretrained(str(transformer_dir))
                except Exception as exc:
                    logger.warning("Failed to load tokenizer: %s", exc)
        elif transformer_dir.exists():
            try:
                from transformers import AutoTokenizer
                self.tokenizer = AutoTokenizer.from_pretrained(str(transformer_dir))
            except Exception:
                pass

        # Load GBM
        gbm_dir = base / "gbm"
        gbm_onnx = gbm_dir / "model.onnx"
        features_path = gbm_dir / "feature_names.json"

        if gbm_onnx.exists():
            try:
                import onnxruntime as ort
                self.gbm_session = ort.InferenceSession(str(gbm_onnx))
                self.gbm_available = True
                logger.info("Loaded GBM ONNX from %s", gbm_onnx)
            except Exception as exc:
                logger.warning("Failed to load GBM ONNX: %s", exc)

        if features_path.exists():
            with open(features_path) as f:
                self.feature_names = json.load(f)

        # Load calibrator
        calibrator_path = base / "calibration.pkl"
        if calibrator_path.exists():
            try:
                from ml.training.calibrate import IsotonicCalibrator
                self.calibrator = IsotonicCalibrator.load(str(calibrator_path))
                logger.info("Loaded calibrator from %s", calibrator_path)
            except Exception as exc:
                logger.warning("Failed to load calibrator: %s", exc)

        logger.info(
            "ModelLoader: transformer=%s gbm=%s calibrator=%s version=%s",
            self.transformer_available,
            self.gbm_available,
            self.calibrator is not None,
            self.model_version,
        )

    def predict_transformer(self, input_ids: Any, attention_mask: Any) -> Any:
        """Run transformer inference. Returns logits array."""
        if not self.transformer_available:
            raise RuntimeError("Transformer model not loaded")
        return self.transformer_session.run(
            None,
            {"input_ids": input_ids, "attention_mask": attention_mask},
        )

    def predict_gbm(self, features: Any) -> Any:
        """Run GBM inference. Returns predictions array."""
        if not self.gbm_available:
            raise RuntimeError("GBM model not loaded")
        input_name = self.gbm_session.get_inputs()[0].name
        return self.gbm_session.run(None, {input_name: features})


def get_loader():
    """Factory: return RemoteModelClient if model_service_url is set, else ModelLoader."""
    if settings.model_service_url:
        logger.info("Using RemoteModelClient (url=%s)", settings.model_service_url)
        return RemoteModelClient(
            base_url=settings.model_service_url,
            timeout_ms=settings.model_service_timeout_ms,
        )
    loader = ModelLoader()
    loader.load()
    return loader
