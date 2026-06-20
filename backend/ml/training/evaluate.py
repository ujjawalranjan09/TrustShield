"""Evaluate a trained scam classifier on a test dataset.

Usage:
    python -m ml.training.evaluate --model ml/artifacts/scam_classifier.joblib --data ml/data/test.json
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


def main():
    parser = argparse.ArgumentParser(description="Evaluate scam classifier")
    parser.add_argument("--model", type=str, required=True, help="Path to .joblib model")
    parser.add_argument("--data", type=str, required=True, help="Path to test JSON data")
    args = parser.parse_args()

    try:
        import joblib
        from sklearn.metrics import classification_report, confusion_matrix
    except ImportError:
        print("ERROR: scikit-learn not installed")
        sys.exit(1)

    model = joblib.load(args.model)
    with open(args.data, "r", encoding="utf-8") as f:
        data = json.load(f)

    texts = [d["text"] for d in data]
    labels = [d["label"] for d in data]

    predictions = model.predict(texts)

    print("=== Classification Report ===")
    print(classification_report(labels, predictions))

    print("=== Confusion Matrix ===")
    cm = confusion_matrix(labels, predictions, labels=sorted(set(labels)))
    print(cm)

    # Per-class accuracy
    print("
=== Per-Class Accuracy ===")
    for label in sorted(set(labels)):
        idx = [i for i, l in enumerate(labels) if l == label]
        correct = sum(1 for i in idx if predictions[i] == label)
        total = len(idx)
        print(f"  {label}: {correct}/{total} ({correct/total*100:.1f}%)")


if __name__ == "__main__":
    main()
