"""Fine-tune IndicBERT/MuRIL for scam classification.

Requires GPU. Exports to ONNX after training.

Usage:
    python -m ml.training.train_transformer --data ml/data/train.json --val ml/data/val.json --output ml/artifacts/transformer
"""

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

LABEL_MAP = {
    "legitimate": 0,
    "otp_harvesting": 1,
    "vishing": 2,
    "remote_access": 3,
    "refund_scam": 4,
    "fake_support": 5,
    "phishing": 6,
    "sim_swap": 7,
}

LABEL_NAMES = {v: k for k, v in LABEL_MAP.items()}


def load_data(path: str) -> list:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def prepare_dataset(data: list):
    """Convert conversations to text + label pairs."""
    texts = []
    labels = []
    for conv in data:
        text = " ".join(m["text"] for m in conv["messages"])
        texts.append(text)
        scam_type = conv.get("scam_type", "none")
        if scam_type == "none" and conv.get("label") == "legitimate":
            labels.append(0)
        else:
            labels.append(LABEL_MAP.get(scam_type, 0))
    return texts, labels


def train(train_data: list, val_data: list, output_dir: str, model_name: str = "ai4bharat/indic-bert"):
    """Fine-tune transformer model."""
    try:
        import torch
        from torch.utils.data import Dataset, DataLoader
        from transformers import AutoTokenizer, AutoModelForSequenceClassification, AdamW, get_linear_schedule_with_warmup
    except ImportError:
        print("ERROR: torch/transformers not installed")
        sys.exit(1)

    train_texts, train_labels = prepare_dataset(train_data)
    val_texts, val_labels = prepare_dataset(val_data)

    print(f"Train: {len(train_texts)} samples, Val: {len(val_texts)} samples")
    print(f"Labels: {len(LABEL_MAP)} classes")

    # Load tokenizer
    print(f"Loading tokenizer from {model_name}...")
    try:
        tokenizer = AutoTokenizer.from_pretrained(model_name)
    except Exception:
        print(f"Failed to load {model_name}, using bert-base-multilingual-cased")
        tokenizer = AutoTokenizer.from_pretrained("bert-base-multilingual-cased")

    # Tokenize
    train_encodings = tokenizer(train_texts, truncation=True, padding=True, max_length=256, return_tensors="pt")
    val_encodings = tokenizer(val_texts, truncation=True, padding=True, max_length=256, return_tensors="pt")

    class ScamDataset(Dataset):
        def __init__(self, encodings, labels):
            self.encodings = encodings
            self.labels = labels
        def __len__(self):
            return len(self.labels)
        def __getitem__(self, idx):
            return {
                "input_ids": self.encodings["input_ids"][idx],
                "attention_mask": self.encodings["attention_mask"][idx],
                "labels": torch.tensor(self.labels[idx], dtype=torch.long),
            }

    train_dataset = ScamDataset(train_encodings, train_labels)
    val_dataset = ScamDataset(val_encodings, val_labels)
    train_loader = DataLoader(train_dataset, batch_size=16, shuffle=True)
    val_loader = DataLoader(val_dataset, batch_size=32)

    # Load model
    print(f"Loading model {model_name}...")
    try:
        model = AutoModelForSequenceClassification.from_pretrained(
            model_name, num_labels=len(LABEL_MAP), ignore_mismatched_sizes=True
        )
    except Exception:
        print(f"Failed to load {model_name}, using bert-base-multilingual-cased")
        model = AutoModelForSequenceClassification.from_pretrained(
            "bert-base-multilingual-cased", num_labels=len(LABEL_MAP)
        )

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model.to(device)
    print(f"Using device: {device}")

    # Training
    optimizer = AdamW(model.parameters(), lr=2e-5)
    total_steps = len(train_loader) * 3
    scheduler = get_linear_schedule_with_warmup(optimizer, num_warmup_steps=total_steps // 10, num_training_steps=total_steps)

    best_val_acc = 0.0
    epochs = 3

    for epoch in range(epochs):
        model.train()
        total_loss = 0
        for batch in train_loader:
            batch = {k: v.to(device) for k, v in batch.items()}
            outputs = model(**batch)
            loss = outputs.loss
            loss.backward()
            optimizer.step()
            scheduler.step()
            optimizer.zero_grad()
            total_loss += loss.item()

        avg_loss = total_loss / len(train_loader)
        print(f"Epoch {epoch + 1}/{epochs} — Loss: {avg_loss:.4f}")

        # Validate
        model.eval()
        correct = 0
        total = 0
        with torch.no_grad():
            for batch in val_loader:
                batch = {k: v.to(device) for k, v in batch.items()}
                outputs = model(**batch)
                preds = outputs.logits.argmax(dim=-1)
                correct += (preds == batch["labels"]).sum().item()
                total += batch["labels"].size(0)

        val_acc = correct / total
        print(f"  Val accuracy: {val_acc:.4f}")

        if val_acc > best_val_acc:
            best_val_acc = val_acc
            os.makedirs(output_dir, exist_ok=True)
            model.save_pretrained(output_dir)
            tokenizer.save_pretrained(output_dir)
            print(f"  Saved best model (accuracy={val_acc:.4f})")

    # Save config
    config = {
        "model_name": model_name,
        "num_labels": len(LABEL_MAP),
        "label_map": {str(v): k for k, v in LABEL_MAP.items()},
        "model_version": f"v{len(os.listdir(output_dir))}",
        "epochs": epochs,
        "best_val_accuracy": best_val_acc,
    }
    with open(os.path.join(output_dir, "config.json"), "w") as f:
        json.dump(config, f, indent=2)

    print(f"\nTraining complete. Best val accuracy: {best_val_acc:.4f}")
    print(f"Model saved to: {output_dir}")
    return model, tokenizer


def main():
    parser = argparse.ArgumentParser(description="Train transformer scam classifier")
    parser.add_argument("--data", type=str, default="ml/data/train.json")
    parser.add_argument("--val", type=str, default="ml/data/val.json")
    parser.add_argument("--output", type=str, default="ml/artifacts/transformer")
    parser.add_argument("--model", type=str, default="ai4bharat/indic-bert")
    args = parser.parse_args()

    base = Path(__file__).resolve().parents[2]
    train_data = load_data(str(base / args.data))
    val_data = load_data(str(base / args.val))

    output = str(base / args.output)
    train(train_data, val_data, output, args.model)


if __name__ == "__main__":
    main()
