"""Gold-set evaluation — CI gate for model quality.

Loads ONNX models + gold-set data and computes macro-F1, per-class F1,
and FP-rate.  Fails the build if quality regresses beyond the baseline.

Usage:
    python -m ml.training.gold_eval --artifacts ml/artifacts --gold ml/data/gold_set.json
    python -m ml.training.gold_eval --update-baseline  # after intentional improvements
"""

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np

logger = logging.getLogger(__name__)

# Import the same label map as the classifier
LABEL_MAP = {
    0: "legitimate",
    1: "otp_harvesting",
    2: "vishing",
    3: "remote_access",
    4: "refund_scam",
    5: "fake_support",
    6: "phishing",
    7: "sim_swap",
}

LABEL_TO_ID = {v: k for k, v in LABEL_MAP.items()}

# Baseline path inside the artifacts directory
BASELINE_REL_PATH = "../baseline/gold_baseline.json"


def load_gold_set(path: str) -> Tuple[List[str], List[int]]:
    """Load gold-set conversations and return (texts, labels)."""
    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    texts = []
    labels = []
    for conv in data:
        text = " ".join(m["text"] for m in conv["messages"])
        texts.append(text)

        scam_type = conv.get("scam_type", "none")
        if scam_type == "none" or scam_type == "legitimate":
            labels.append(0)
        else:
            labels.append(LABEL_TO_ID.get(scam_type, 0))

    return texts, labels


def run_transformer_inference(
    texts: List[str], artifacts_dir: str
) -> Tuple[np.ndarray, bool]:
    """Run transformer ONNX on texts. Returns (probas, success)."""
    from app.services.nlp.model_loader import ModelLoader

    loader = ModelLoader()
    loader.load(artifacts_dir)

    if not loader.transformer_available:
        logger.warning("Transformer model not available")
        return np.array([]), False

    all_probas = []
    for text in texts:
        # Tokenize
        if loader.tokenizer is None:
            return np.array([]), False

        if hasattr(loader.tokenizer, "encode"):
            encoding = loader.tokenizer.encode(text)
            input_ids = np.array([encoding.ids], dtype=np.int64)
            attention_mask = np.array([encoding.attention_mask], dtype=np.int64)
        else:
            encoding = loader.tokenizer(
                text, truncation=True, padding=True,
                max_length=256, return_tensors="np",
            )
            input_ids = encoding["input_ids"]
            attention_mask = encoding["attention_mask"]

        # Run inference
        outputs = loader.predict_transformer(input_ids, attention_mask)
        logits = outputs[0][0]

        # Softmax
        exp_logits = np.exp(logits - np.max(logits))
        probas = exp_logits / exp_logits.sum()
        all_probas.append(probas)

    return np.array(all_probas), True


def run_gbm_inference(
    texts: List[str], artifacts_dir: str
) -> Tuple[np.ndarray, bool]:
    """Run GBM ONNX on texts. Returns (probas, success)."""
    from app.services.nlp.model_loader import ModelLoader
    from ml.training.features import extract_features, get_feature_names

    loader = ModelLoader()
    loader.load(artifacts_dir)

    if not loader.gbm_available:
        logger.warning("GBM model not available")
        return np.array([]), False

    feature_names = get_feature_names()
    all_probas = []

    for text in texts:
        messages = [{"sender": "unknown", "text": text}]
        features = extract_features(messages)
        feature_vector = np.array(
            [[features.get(name, 0.0) for name in feature_names]],
            dtype=np.float32,
        )

        outputs = loader.predict_gbm(feature_vector)
        logits = outputs[0][0]

        exp_logits = np.exp(logits - np.max(logits))
        probas = exp_logits / exp_logits.sum()
        all_probas.append(probas)

    return np.array(all_probas), True


def compute_metrics(
    predictions: List[int], labels: List[int]
) -> Dict:
    """Compute macro-F1, per-class F1, and FP-rate."""
    from sklearn.metrics import (
        confusion_matrix,
        f1_score,
        precision_recall_fscore_support,
    )

    macro_f1 = round(f1_score(labels, predictions, average="macro"), 4)

    per_class = precision_recall_fscore_support(
        labels, predictions, labels=list(LABEL_MAP.keys()), zero_division=0
    )
    per_class_f1 = {
        LABEL_MAP[i]: round(per_class[2][idx], 4)
        for idx, i in enumerate(range(len(LABEL_MAP)))
    }

    # FP-rate: false positives / (false positives + true negatives)
    # For multiclass, use one-vs-rest micro-averaging.
    # - FP for class c = column_sum(c) - diagonal(c)  (predicted c but actually other class)
    # - TN for class c = total - row_sum(c) - column_sum(c) + diagonal(c)
    cm = confusion_matrix(labels, predictions, labels=list(LABEL_MAP.keys()))
    total = cm.sum()
    fp_per_class = cm.sum(axis=0) - cm.diagonal()       # predicted c but actually another class
    total_fp = fp_per_class.sum()
    # TN for class c = total - (actual c) - (predicted c) + (correct c)
    actual_per_class = cm.sum(axis=1)
    predicted_per_class = cm.sum(axis=0)
    correct_per_class = cm.diagonal()
    total_true_negatives = (
        total * cm.shape[0]
        - actual_per_class.sum()
        - predicted_per_class.sum()
        + correct_per_class.sum()
    )
    # Simpler & correct micro OvR: TN = sum over classes of (total - actual_c - predicted_c + correct_c)
    # total over all classes / num_classes to avoid overcounting.
    n_classes = cm.shape[0]
    total_true_negatives = (
        (n_classes * total) - actual_per_class.sum() - predicted_per_class.sum() + correct_per_class.sum()
    ) / n_classes if n_classes > 0 else 0
    denom = total_fp + total_true_negatives
    fp_rate = round(float(total_fp) / denom, 4) if denom > 0 else 0.0

    # Accuracy
    accuracy = round(
        sum(1 for p, l in zip(predictions, labels) if p == l) / len(labels), 4
    )

    return {
        "macro_f1": macro_f1,
        "accuracy": accuracy,
        "fp_rate": fp_rate,
        "per_class_f1": per_class_f1,
        "n_samples": len(labels),
    }


def load_baseline(baseline_path: str) -> Dict:
    """Load the committed baseline metrics."""
    path = Path(baseline_path)
    if not path.exists():
        logger.warning("Baseline not found at %s", baseline_path)
        return {"macro_f1": 0.0, "fp_rate": 1.0}
    with open(path) as f:
        return json.load(f)


def save_baseline(baseline_path: str, metrics: Dict) -> None:
    """Save updated baseline metrics."""
    path = Path(baseline_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    baseline = {
        "macro_f1": metrics["macro_f1"],
        "fp_rate": metrics["fp_rate"],
        "accuracy": metrics["accuracy"],
        "per_class_f1": metrics["per_class_f1"],
        "n_samples": metrics["n_samples"],
        "timestamp": __import__("datetime").datetime.now().isoformat(),
    }
    with open(path, "w") as f:
        json.dump(baseline, f, indent=2)
    logger.info("Baseline saved to %s", baseline_path)


def main():
    parser = argparse.ArgumentParser(
        description="Evaluate ONNX models on gold set and compare against baseline"
    )
    parser.add_argument(
        "--artifacts", default="ml/artifacts",
        help="Path to the artifacts directory",
    )
    parser.add_argument(
        "--gold", default="ml/data/gold_set.json",
        help="Path to gold-set JSON",
    )
    parser.add_argument(
        "--update-baseline", action="store_true",
        help="Update the committed baseline (requires human review)",
    )
    parser.add_argument(
        "--macro-f1-threshold", type=float, default=0.90,
        help="Minimum acceptable macro-F1",
    )
    parser.add_argument(
        "--fp-rate-threshold", type=float, default=0.02,
        help="Maximum acceptable FP-rate (2%%)",
    )
    parser.add_argument(
        "--regression-points", type=float, default=0.01,
        help="Maximum allowed regression from baseline (1 point = 0.01)",
    )
    parser.add_argument(
        "--output", default="gold_report.json",
        help="Output path for the gold report JSON",
    )
    args = parser.parse_args()

    base = Path(__file__).resolve().parents[2]
    artifacts_dir = str(base / args.artifacts)
    gold_path = str(base / args.gold)

    # Load gold set
    logger.info("Loading gold set from %s", gold_path)
    texts, labels = load_gold_set(gold_path)
    logger.info("Gold set: %d samples, %d classes", len(texts), len(set(labels)))

    # Run inference
    # Try transformer first, then GBM, then fail
    probas, success = run_transformer_inference(texts, artifacts_dir)
    model_used = "transformer"

    if not success:
        logger.info("Transformer unavailable, trying GBM...")
        probas, success = run_gbm_inference(texts, artifacts_dir)
        model_used = "gbm"

    if not success:
        logger.error("No models available for evaluation!")
        sys.exit(1)

    # Get predictions
    predictions = [int(np.argmax(p)) for p in probas]

    # Compute metrics
    metrics = compute_metrics(predictions, labels)
    metrics["model_used"] = model_used

    # Print report
    print("\n=== Gold-Set Evaluation Report ===")
    print(f"Model used: {model_used}")
    print(f"Macro-F1:   {metrics['macro_f1']}")
    print(f"Accuracy:   {metrics['accuracy']}")
    print(f"FP-rate:    {metrics['fp_rate']}")
    print(f"Samples:    {metrics['n_samples']}")
    print("\nPer-class F1:")
    for cls, f1 in sorted(metrics["per_class_f1"].items()):
        print(f"  {cls}: {f1}")
    print()

    # Load baseline
    baseline_path = str(base / "ml" / "baseline" / "gold_baseline.json")
    baseline = load_baseline(baseline_path)

    # Check thresholds
    passed = True
    failures = []

    if metrics["macro_f1"] < args.macro_f1_threshold:
        passed = False
        failures.append(
            f"Macro-F1 {metrics['macro_f1']} < threshold {args.macro_f1_threshold}"
        )

    if metrics["fp_rate"] > args.fp_rate_threshold:
        passed = False
        failures.append(
            f"FP-rate {metrics['fp_rate']} > threshold {args.fp_rate_threshold}"
        )

    # Check regression against baseline
    if baseline.get("macro_f1", 0) > 0:
        regression = baseline["macro_f1"] - metrics["macro_f1"]
        if regression > args.regression_points:
            passed = False
            failures.append(
                f"Macro-F1 regressed by {regression:.4f} points "
                f"(baseline={baseline['macro_f1']}, new={metrics['macro_f1']})"
            )

    # Save report
    report = {
        "timestamp": __import__("datetime").datetime.now().isoformat(),
        "gold_set": args.gold,
        "n_samples": metrics["n_samples"],
        "model_used": model_used,
        "macro_f1": metrics["macro_f1"],
        "accuracy": metrics["accuracy"],
        "fp_rate": metrics["fp_rate"],
        "per_class_f1": metrics["per_class_f1"],
        "baseline": baseline,
        "passed": passed,
        "failures": failures,
    }

    output_path = Path(args.output)
    if not output_path.is_absolute():
        output_path = base / args.output
    with open(output_path, "w") as f:
        json.dump(report, f, indent=2)
    logger.info("Report saved to %s", output_path)

    # Update baseline if requested
    if args.update_baseline:
        save_baseline(baseline_path, metrics)

    # Exit with status
    if not passed:
        print("❌ GOLD-SET EVALUATION FAILED")
        for f in failures:
            print(f"  - {f}")
        sys.exit(1)

    print("✅ Gold-set evaluation PASSED")
    sys.exit(0)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()