"""Train XGBoost classifier on engineered features.

Usage:
    python -m ml.training.train_gbm --data ml/data/train.json --val ml/data/val.json --output ml/artifacts/gbm
"""

import argparse
import json
import os
import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


def load_data(path: str) -> list:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def main():
    parser = argparse.ArgumentParser(description="Train GBM scam classifier")
    parser.add_argument("--data", type=str, default="ml/data/train.json")
    parser.add_argument("--val", type=str, default="ml/data/val.json")
    parser.add_argument("--output", type=str, default="ml/artifacts/gbm")
    args = parser.parse_args()

    base = Path(__file__).resolve().parents[2]

    from ml.training.features import conversations_to_feature_matrix

    train_data = load_data(str(base / args.data))
    val_data = load_data(str(base / args.val))

    print(f"Extracting features from {len(train_data)} train, {len(val_data)} val conversations...")
    X_train, y_train, feature_names = conversations_to_feature_matrix(train_data)
    X_val, y_val, _ = conversations_to_feature_matrix(val_data)

    print(f"Feature matrix shape: {X_train.shape}")
    print(f"Feature names: {len(feature_names)}")

    try:
        import xgboost as xgb
        from sklearn.metrics import classification_report, f1_score
    except ImportError:
        print("ERROR: xgboost not installed. Run: pip install xgboost")
        sys.exit(1)

    print("Training XGBoost...")
    model = xgb.XGBClassifier(
        n_estimators=200,
        max_depth=6,
        learning_rate=0.1,
        objective="multi:softprob",
        num_class=8,
        eval_metric="mlogloss",
        use_label_encoder=False,
        random_state=42,
        n_jobs=-1,
    )

    model.fit(
        X_train, y_train,
        eval_set=[(X_val, y_val)],
        verbose=50,
    )

    # Evaluate
    y_pred = model.predict(X_val)
    val_f1 = f1_score(y_val, y_pred, average="macro")
    print(f"\nVal macro-F1: {val_f1:.4f}")
    print(classification_report(y_val, y_pred))

    # Feature importance
    importance = dict(zip(feature_names, model.feature_importances_.tolist()))

    # Save
    output_dir = str(base / args.output)
    os.makedirs(output_dir, exist_ok=True)

    model.save_model(os.path.join(output_dir, "model.json"))

    with open(os.path.join(output_dir, "feature_names.json"), "w") as f:
        json.dump(feature_names, f)

    with open(os.path.join(output_dir, "feature_importance.json"), "w") as f:
        json.dump(importance, f, indent=2)

    metrics = {
        "val_f1_macro": round(val_f1, 4),
        "num_features": len(feature_names),
        "num_classes": 8,
        "train_size": len(X_train),
        "val_size": len(X_val),
    }
    with open(os.path.join(output_dir, "metrics.json"), "w") as f:
        json.dump(metrics, f, indent=2)

    metadata = {
        "model_type": "xgboost",
        "num_features": len(feature_names),
        "feature_names": feature_names,
        "hyperparams": {
            "n_estimators": 200,
            "max_depth": 6,
            "learning_rate": 0.1,
        },
    }
    with open(os.path.join(output_dir, "metadata.json"), "w") as f:
        json.dump(metadata, f, indent=2)

    print(f"\nModel saved to: {output_dir}")
    print(f"Metrics: {metrics}")


if __name__ == "__main__":
    main()
