"""Explanation backends — TreeSHAP for GBM, occlusion for transformer.

At serving time, merges attributions from both models into a unified
ShapAttribution list for the API response.
"""

import logging
from typing import List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)


class GBMExplainer:
    """TreeSHAP explainer for the GBM model."""

    def __init__(self):
        self._explainer = None
        self._model = None
        self._feature_names: List[str] = []

    def load(self, artifacts_dir: str = "ml/artifacts/gbm"):
        try:
            import xgboost as xgb
            import shap
            import json
            from pathlib import Path

            base = Path(artifacts_dir)
            model_path = base / "model.json"
            features_path = base / "feature_names.json"

            if not model_path.exists():
                logger.info("GBM model not found at %s", model_path)
                return

            self._model = xgb.XGBClassifier()
            self._model.load_model(str(model_path))

            if features_path.exists():
                with open(features_path) as f:
                    self._feature_names = json.load(f)

            self._explainer = shap.TreeExplainer(self._model)
            logger.info("GBM TreeSHAP explainer loaded")
        except ImportError:
            logger.warning("shap or xgboost not installed, GBM explainer disabled")
        except Exception as exc:
            logger.warning("Failed to load GBM explainer: %s", exc)

    def explain(self, features: np.ndarray) -> Optional[List[Tuple[str, float, float]]]:
        """Return (feature_name, feature_value, shap_value) tuples."""
        if self._explainer is None:
            return None

        try:
            shap_values = self._explainer.shap_values(features)
            if isinstance(shap_values, list):
                shap_values = shap_values[1]  # scam class for binary

            if len(shap_values.shape) > 1:
                shap_values = shap_values[0]

            feature_values = features[0] if len(features.shape) > 1 else features

            results = []
            for i, name in enumerate(self._feature_names):
                results.append((name, float(feature_values[i]), float(shap_values[i])))

            results.sort(key=lambda x: abs(x[2]), reverse=True)
            return results[:10]
        except Exception as exc:
            logger.warning("GBM SHAP explanation failed: %s", exc)
            return None


class TransformerExplainer:
    """Token occlusion explainer for the transformer (black-box ONNX safe)."""

    def __init__(self):
        self._loader = None

    def _get_loader(self):
        if self._loader is None:
            from app.services.nlp.model_loader import ModelLoader
            self._loader = ModelLoader()
        return self._loader

    def explain(self, text: str) -> Optional[List[Tuple[str, float, float]]]:
        """Occlusion-based explanation for transformer.

        Masks each token and measures probability change.
        Returns list of (token, original_prob, delta_prob).
        """
        loader = self._get_loader()
        if not loader.transformer_available or loader.tokenizer is None:
            return None

        try:
            import numpy as np

            # Tokenize full text
            if hasattr(loader.tokenizer, "encode"):
                encoding = loader.tokenizer.encode(text)
                tokens = encoding.tokens
                input_ids = np.array([encoding.ids], dtype=np.int64)
                attention_mask = np.array([encoding.attention_mask], dtype=np.int64)
            else:
                enc = loader.tokenizer(text, truncation=True, max_length=256, return_tensors="np")
                input_ids = enc["input_ids"]
                attention_mask = enc["attention_mask"]
                tokens = loader.tokenizer.convert_ids_to_tokens(input_ids[0])

            # Get baseline prediction
            outputs = loader.predict_transformer(input_ids, attention_mask)
            logits = outputs[0][0]
            exp_logits = np.exp(logits - np.max(logits))
            probs = exp_logits / exp_logits.sum()
            scam_prob = float(probs[1]) if len(probs) > 1 else float(probs[0])
            predicted_class = int(np.argmax(probs))

            # Occlude each token (replace with PAD)
            results = []
            pad_token = loader.tokenizer.pad_token_id if hasattr(loader.tokenizer, "pad_token_id") else 0
            n_tokens = min(len(tokens), 50)  # limit for speed

            for i in range(1, n_tokens):  # skip [CLS]
                masked_ids = input_ids.copy()
                masked_ids[0, i] = pad_token
                masked_mask = attention_mask.copy()
                masked_mask[0, i] = 0

                out = loader.predict_transformer(masked_ids, masked_mask)
                masked_logits = out[0][0]
                masked_exp = np.exp(masked_logits - np.max(masked_logits))
                masked_probs = masked_exp / masked_exp.sum()
                masked_scam_prob = float(masked_probs[predicted_class])

                delta = scam_prob - masked_scam_prob
                token = tokens[i] if i < len(tokens) else f"token_{i}"
                results.append((token, scam_prob, delta))

            results.sort(key=lambda x: abs(x[2]), reverse=True)
            return results[:10]
        except Exception as exc:
            logger.warning("Transformer occlusion explanation failed: %s", exc)
            return None


class ExplainerManager:
    """Merges attributions from both models."""

    def __init__(self):
        self.gbm = GBMExplainer()
        self.transformer = TransformerExplainer()

    def load(self, artifacts_dir: str = "ml/artifacts"):
        self.gbm.load(f"{artifacts_dir}/gbm")

    def explain(self, text: str, features: Optional[np.ndarray] = None) -> List[dict]:
        """Get merged explanations from both models."""
        attributions = []

        # GBM TreeSHAP
        if features is not None:
            gbm_results = self.gbm.explain(features)
            if gbm_results:
                for name, value, shap_val in gbm_results:
                    attributions.append({
                        "feature": name,
                        "value": round(value, 4),
                        "shap_value": round(shap_val, 4),
                        "direction": "increases" if shap_val > 0 else "decreases",
                        "source": "gbm",
                    })

        # Transformer occlusion
        transformer_results = self.transformer.explain(text)
        if transformer_results:
            for token, prob, delta in transformer_results:
                attributions.append({
                    "feature": f"token:{token}",
                    "value": round(prob, 4),
                    "shap_value": round(delta, 4),
                    "direction": "increases" if delta > 0 else "decreases",
                    "source": "transformer",
                })

        attributions.sort(key=lambda x: abs(x["shap_value"]), reverse=True)
        return attributions[:10]


# Singleton
_explainer: Optional[ExplainerManager] = None


def get_explainer() -> ExplainerManager:
    global _explainer
    if _explainer is None:
        _explainer = ExplainerManager()
        _explainer.load()
    return _explainer
