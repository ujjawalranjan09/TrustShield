import json
import os
import random
import uuid
from datetime import datetime, timedelta


def generate_dataset():
    data = []

    scam_types = ["vishing", "fake_support", "refund_scam"]
    languages = ["en", "hi", "hinglish", "mixed"]

    scam_templates = [
        (
            "hinglish",
            "vishing",
            [
                {
                    "sender": "agent",
                    "text": "Hello sir, I am calling from bank. aapka debit card block ho gaya hai.",
                },
                {"sender": "user", "text": "what? why?"},
                {
                    "sender": "agent",
                    "text": "bhai apna OTP batao verify karne ke liye, phir unblock hoga.",
                },
            ],
        ),
        (
            "mixed",
            "fake_support",
            [
                {
                    "sender": "agent",
                    "text": "Aapko refund process karne ke liye ek baar screen share karo.",
                },
                {"sender": "user", "text": "Kaise karu?"},
                {
                    "sender": "agent",
                    "text": "AnyDesk app download kijiye aur code bataiye: 123456789.",
                },
            ],
        ),
        (
            "hinglish",
            "refund_scam",
            [
                {
                    "sender": "agent",
                    "text": "Sir, your refund of Rs 5000 is approved. Please scan this QR code.",
                },
                {"sender": "user", "text": "Okay send it."},
                {
                    "sender": "agent",
                    "text": "I have sent the link. Payment receive karne ke liye PIN enter karein.",
                },
            ],
        ),
        (
            "en",
            "vishing",
            [
                {
                    "sender": "agent",
                    "text": "Hello, this is Amazon support. Your account is compromised.",
                },
                {"sender": "user", "text": "Oh no, what should I do?"},
                {
                    "sender": "agent",
                    "text": "Please provide your OTP so we can secure your account immediately.",
                },
            ],
        ),
    ]

    legit_templates = [
        (
            "en",
            "none",
            [
                {"sender": "user", "text": "Hi, when will my order be delivered?"},
                {
                    "sender": "agent",
                    "text": "Your order will be delivered by tomorrow 8 PM.",
                },
                {"sender": "user", "text": "Thanks."},
            ],
        ),
        (
            "hinglish",
            "none",
            [
                {"sender": "user", "text": "Bhai kal kitne baje aana hai?"},
                {"sender": "friend", "text": "10 baje aa jana, meeting hai."},
                {"sender": "user", "text": "Okay, see you."},
            ],
        ),
        (
            "mixed",
            "none",
            [
                {"sender": "user", "text": "I need help with my account statement."},
                {
                    "sender": "agent",
                    "text": "Sure, aap apna email check karein, humne statement bhej diya hai.",
                },
                {"sender": "user", "text": "Mil gaya, thank you."},
            ],
        ),
    ]

    start_time = datetime.now()

    for i in range(600):
        lang, s_type, msgs = random.choice(scam_templates)

        formatted_msgs = []
        t = start_time - timedelta(days=random.randint(1, 30))
        for msg in msgs:
            formatted_msgs.append(
                {
                    "sender": msg["sender"],
                    "text": msg["text"],
                    "timestamp": t.isoformat(),
                }
            )
            t += timedelta(minutes=1)

        data.append(
            {
                "id": str(uuid.uuid4()),
                "messages": formatted_msgs,
                "label": "scam",
                "scam_type": s_type,
                "language": lang,
                "flagged_entities": ["123456789"]
                if "123456789" in json.dumps(msgs)
                else [],
            }
        )

    for i in range(400):
        lang, s_type, msgs = random.choice(legit_templates)

        formatted_msgs = []
        t = start_time - timedelta(days=random.randint(1, 30))
        for msg in msgs:
            formatted_msgs.append(
                {
                    "sender": msg["sender"],
                    "text": msg["text"],
                    "timestamp": t.isoformat(),
                }
            )
            t += timedelta(minutes=1)

        data.append(
            {
                "id": str(uuid.uuid4()),
                "messages": formatted_msgs,
                "label": "legitimate",
                "scam_type": s_type,
                "language": lang,
                "flagged_entities": [],
            }
        )

    random.shuffle(data)

    output_path = "backend/ml/data/raw/scam_conversations.json"
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(data, f, indent=2)


if __name__ == "__main__":
    generate_dataset()
