import json
import random
import uuid
from copy import deepcopy
import os

# Stub for LLM call
def augment_text(text, variant_idx):
    # Mocking data augmentation
    return f"{text} (Variant {variant_idx})"

def run_augmentation():
    input_path = os.path.join(os.path.dirname(__file__), "../data/raw/scam_conversations.json")
    output_path = os.path.join(os.path.dirname(__file__), "../data/augmented/augmented_conversations.json")

    with open(input_path, "r") as f:
        data = json.load(f)

    augmented_data = []

    for item in data:
        if item["label"] == "scam":
            for i in range(1, 6):
                new_item = deepcopy(item)
                new_item["id"] = str(uuid.uuid4())
                new_item["augmented_from"] = item["id"]

                for msg in new_item["messages"]:
                    msg["text"] = augment_text(msg["text"], i)

                augmented_data.append(new_item)

    with open(output_path, "w") as f:
        json.dump(augmented_data, f, indent=2)

if __name__ == "__main__":
    run_augmentation()
