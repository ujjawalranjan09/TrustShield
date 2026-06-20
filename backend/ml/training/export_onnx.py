"""Export trained models to ONNX format.

Usage:
    python -m ml.training.export_onnx --model-type gbm --input ml/artifacts/gbm --output ml/artifacts/gbm
    python -m ml.training.export_onnx --model-type transformer --input ml/artifacts/transformer --output ml/artifacts/transformer
"""

import argparse
import json
import os
import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


def export_gbm_to_onnx(input_dir: str, output_dir: str):
    """Export XGBoost model to ONNX."""
    try:
        import xgboost as xgb
        from skl2onnx import convert_sklearn
        from skl2onnx.common.data_types import FloatTensorType
    except ImportError:
        print("ERROR: xgboost and skl2onnx required. Run: pip install xgboost skl2onnx")
        sys.exit(1)

    model = xgb.XGBClassifier()
    model.load_model(os.path.join(input_dir, "model.json"))

    with open(os.path.join(input_dir, "feature_names.json")) as f:
        feature_names = json.load(f)

    n_features = len(feature_names)
    initial_type = [("float_input", FloatTensorType([None, n_features]))]

    onnx_model = convert_sklearn(model, initial_types=initial_type)

    os.makedirs(output_dir, exist_ok=True)
    onnx_path = os.path.join(output_dir, "model.onnx")
    with open(onnx_path, "wb") as f:
        f.write(onnx_model.SerializeToString())
    print(f"GBM ONNX exported to: {onnx_path}")


def export_transformer_to_onnx(input_dir: str, output_dir: str):
    """Export transformer model to ONNX using optimum."""
    try:
        import torch
        from transformers import AutoModelForSequenceClassification, AutoTokenizer
        from optimum.onnxruntime import ORTModelForSequenceClassification
    except ImportError:
        print("ERROR: transformers, optimum, onnxruntime required")
        sys.exit(1)

    with open(os.path.join(input_dir, "config.json")) as f:
        _config = json.load(f)

    os.makedirs(output_dir, exist_ok=True)

    try:
        ort_model = ORTModelForSequenceClassification.from_pretrained(
            input_dir, export=True
        )
        ort_model.save_pretrained(output_dir)
        print(f"Transformer ONNX exported to: {output_dir}")
    except Exception as exc:
        print(f"optimum export failed: {exc}")
        print("Falling back to manual ONNX export...")

        model = AutoModelForSequenceClassification.from_pretrained(input_dir)
        tokenizer = AutoTokenizer.from_pretrained(input_dir)

        dummy = tokenizer("test message", return_tensors="pt", truncation=True, padding=True, max_length=256)

        torch.onnx.export(
            model,
            (dummy["input_ids"], dummy["attention_mask"]),
            os.path.join(output_dir, "model.onnx"),
            input_names=["input_ids", "attention_mask"],
            output_names=["logits"],
            dynamic_axes={"input_ids": {0: "batch", 1: "seq"}, "attention_mask": {0: "batch", 1: "seq"}},
            opset_version=14,
        )
        tokenizer.save_pretrained(output_dir)
        print(f"Transformer ONNX exported (manual) to: {output_dir}")


def main():
    parser = argparse.ArgumentParser(description="Export models to ONNX")
    parser.add_argument("--model-type", choices=["gbm", "transformer"], required=True)
    parser.add_argument("--input", type=str, required=True)
    parser.add_argument("--output", type=str, required=True)
    args = parser.parse_args()

    base = Path(__file__).resolve().parents[2]
    input_dir = str(base / args.input)
    output_dir = str(base / args.output)

    if args.model_type == "gbm":
        export_gbm_to_onnx(input_dir, output_dir)
    else:
        export_transformer_to_onnx(input_dir, output_dir)


if __name__ == "__main__":
    main()
