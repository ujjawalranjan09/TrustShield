"""Full ML pipeline orchestrator.

Runs: data generation → training → evaluation → ONNX export → MLflow logging.

Usage:
    python -m ml.training.run_pipeline
    python -m ml.training.run_pipeline --skip-transformer  # GBM only
    python -m ml.training.run_pipeline --skip-gbm  # Transformer only
"""

import argparse
import json
import os
import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


def load_data(path: str) -> list:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def evaluate_model(predictions: list, labels: list) -> dict:
    """Compute classification metrics."""
    from sklearn.metrics import f1_score, precision_score, recall_score

    return {
        "f1_macro": round(f1_score(labels, predictions, average="macro"), 4),
        "precision_macro": round(precision_score(labels, predictions, average="macro"), 4),
        "recall_macro": round(recall_score(labels, predictions, average="macro"), 4),
    }


def main():
    parser = argparse.ArgumentParser(description="Run full ML pipeline")
    parser.add_argument("--skip-transformer", action="store_true")
    parser.add_argument("--skip-gbm", action="store_true")
    parser.add_argument("--skip-export", action="store_true")
    parser.add_argument("--artifacts-dir", default="ml/artifacts")
    args = parser.parse_args()

    base = Path(__file__).resolve().parents[2]
    os.chdir(base)

    print("=" * 60)
    print("TrustShield ML Pipeline")
    print(f"Started: {datetime.now().isoformat()}")
    print("=" * 60)

    # 1. Verify data exists
    data_dir = base / "ml" / "data"
    for split in ["train.json", "val.json", "test.json", "gold_set.json"]:
        path = data_dir / split
        if not path.exists():
            print(f"ERROR: {split} not found. Run generate_corpus.py first.")
            sys.exit(1)
        count = len(load_data(str(path)))
        print(f"  {split}: {count} conversations")

    train_data = load_data(str(data_dir / "train.json"))
    val_data = load_data(str(data_dir / "val.json"))
    test_data = load_data(str(data_dir / "test.json"))
    gold_data = load_data(str(data_dir / "gold_set.json"))

    # 2. Train models
    gbm_metrics = {}

    if not args.skip_transformer:
        print("\n--- Training Transformer ---")
        try:
            from ml.training.train_transformer import train as train_transformer
            transformer_dir = str(base / args.artifacts_dir / "transformer")
            train_transformer(train_data, val_data, transformer_dir)
            print("Transformer training complete")
        except Exception as exc:
            print(f"Transformer training failed: {exc}")
            print("Continuing with GBM only...")

    if not args.skip_gbm:
        print("\n--- Training GBM ---")
        try:
            from ml.training.train_gbm import main as train_gbm_main
            sys.argv = ["train_gbm"]
            train_gbm_main()

            # Load metrics
            metrics_path = base / args.artifacts_dir / "gbm" / "metrics.json"
            if metrics_path.exists():
                with open(metrics_path) as f:
                    gbm_metrics = json.load(f)
                print(f"GBM val F1: {gbm_metrics.get('val_f1_macro', 'N/A')}")
        except Exception as exc:
            print(f"GBM training failed: {exc}")

    # 3. Export ONNX
    if not args.skip_export:
        print("\n--- Exporting ONNX ---")
        if not args.skip_gbm:
            try:
                from ml.training.export_onnx import export_gbm_to_onnx
                export_gbm_to_onnx(
                    str(base / args.artifacts_dir / "gbm"),
                    str(base / args.artifacts_dir / "gbm"),
                )
            except Exception as exc:
                print(f"GBM ONNX export failed: {exc}")

        if not args.skip_transformer:
            try:
                from ml.training.export_onnx import export_transformer_to_onnx
                export_transformer_to_onnx(
                    str(base / args.artifacts_dir / "transformer"),
                    str(base / args.artifacts_dir / "transformer"),
                )
            except Exception as exc:
                print(f"Transformer ONNX export failed: {exc}")

    # 4. Log to MLflow
    print("\n--- Logging to MLflow ---")
    try:
        from ml.training.mlflow_config import setup_mlflow, log_training_run

        if setup_mlflow():
            params = {
                "train_size": len(train_data),
                "val_size": len(val_data),
                "test_size": len(test_data),
                "gold_size": len(gold_data),
            }
            metrics = {}
            metrics.update(gbm_metrics)

            log_training_run(
                model_type="ensemble",
                params=params,
                metrics=metrics,
                artifacts_dir=str(base / args.artifacts_dir),
                tags={"pipeline_version": "v1", "date": datetime.now().strftime("%Y-%m-%d")},
            )
    except Exception as exc:
        print(f"MLflow logging failed: {exc}")

    # 5. Summary
    print("\n" + "=" * 60)
    print("Pipeline Complete")
    print(f"Finished: {datetime.now().isoformat()}")
    print(f"Artifacts: {base / args.artifacts_dir}")
    print("=" * 60)


if __name__ == "__main__":
    main()
