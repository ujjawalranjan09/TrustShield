"""Independent gold set generator — NO shared code with generate_corpus.py.

Uses its own template tables, its own synonym lists, its own sentence
structures. This ensures the gold set is methodologically independent
of the training generator.

Generates ~400 synthetic examples + expects ~1400 real examples to be
manually added. Total target: 2,000 held-out examples.

Usage:
    python -m ml.training.gold_generator
"""

import json
import os
import random
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

# Completely independent template bank — different phrasings, different structure
GOLD_TEMPLATES = {
    "otp_harvesting": [
        "Aapka verification code kya hai? Mujhe batana padega",
        "Ek baar jo code aaya hai SMS mein wo forward kar do",
        "Mujhe aapka login code chahiye for security check",
        "Your authentication code is needed to unlock your account",
        "Please provide the 6-digit code sent to your mobile",
        "Code share karo turant, warna login blocked ho jayega",
        "Aapke phone pe ek code aaya hoga, wo mujhe bhejo",
        "Security verification ke liye OTP dijiye",
    ],
    "vishing": [
        "RBI kehta hai aapka account suspicious hai",
        "Aapka bank account suspend hone wala hai",
        "Account closing within 24 hours unless you verify",
        "Your bank flagged unusual activity. Call back immediately.",
        "This is the compliance department. Your account is under review.",
        "KYC update mandatory hai, nahi toh account band",
        "ATM se paisa nahi niklega agar verify nahi kiya",
        "Your debit card has been temporarily blocked for security",
    ],
    "remote_access": [
        "Screen share karna padega for troubleshooting",
        "AnyDesk ya TeamViewer install karo please",
        "Remote connection chahiye aapke phone pe",
        "Your device has malware. Let us access it remotely.",
        "Download this support tool for immediate fix",
        "We need to view your screen to resolve the issue",
        "Technical team ko access chahiye aapke device ka",
        "Please install remote desktop app for bank support",
    ],
    "refund_scam": [
        "Refund ke liye QR scan karo with your PIN",
        "Aapka paisa wapas aayega agar ye code scan karoge",
        "UPI QR scan karo aur PIN daalo, refund mil jayega",
        "Your cashback requires QR verification with PIN",
        "Scan to receive your pending refund amount",
        "Payment reversal ke liye ye link open karo",
        "Refund receive karne ka ye fastest method hai",
        "QR code pe click karo aur PIN enter karo for refund",
    ],
    "fake_support": [
        "Bank customer care se bol raha hu, aapka issue resolve karna hai",
        "Hum aapki madad karenge, bas card number batao",
        "Support team here. We need your account details for verification.",
        "Your complaint is being processed. Share your IFSC code.",
        "We are the authorized support team. Please cooperate.",
        "Account verification ke liye DOB aur mother name batao",
        "Technical support hai, card details chahiye for refund",
        "Complaint reference ke liye aapka account number dijiye",
    ],
    "phishing": [
        "Ye link open karo for KYC update: {url}",
        "Account verification ke liye click here: {url}",
        "Your account will be deleted. Verify at: {url}",
        "Prize jeeto! Link pe click karo: {url}",
        "Urgent: update your details at this secure portal",
        "Bank ne aapko link bheja hai for verification",
        "Click this to prevent account suspension: {url}",
        "KYC renewal required. Visit: {url}",
    ],
    "sim_swap": [
        "Naya SIM activate karne ke liye OTP chahiye",
        "Your SIM needs reactivation. Share the code.",
        "SIM porting ke liye verification code do",
        "New SIM card ready hai, OTP se activate karo",
        "Network upgrade ke liye OTP share karo please",
        "SIM replacement complete. Now verify with OTP.",
        "Your old SIM is deactivated. New one needs OTP.",
        "Telecom verification: please share the activation code",
    ],
    "legitimate": [
        "Meeting kab hai? Kal ya parson?",
        "Report bhej diya email pe. Check karo.",
        "Package deliver ho gaya kya? Tracking dikha raha hai.",
        "Lunch ke liye kahan chalna hai?",
        "Flight ka time kya hai kal?",
        "Gym jana hai aaj. Saath chalein?",
        "Rent bhej diya. UTR number: 123456789",
        "Doctor ka appointment fix ho gaya.",
        "Movie ka ticket book kar liya.",
        "Password change kar diya hai. New password: abc123",
        "Client ko proposal bhej diya hai.",
        "Team dinner confirm hai kal raat ko.",
    ],
}

# Independent URL pool (different from generate_corpus.py)
GOLD_URLS = [
    "http://mybank-secure-login.com/verify",
    "http://account-safety-check.in/kyc",
    "http://official-bank-update.co.in/urgent",
    "http://prize-winner-2026.in/claim",
    "http://secure-payment-portal.com/refund",
]

# Independent synonym pool
GOLD_NAMES = ["Suresh", "Meena", "Kiran", "Anita", "Prakash", "Geeta", "Sunil", "Kavita"]
GOLD_BANKS = ["HDFC Bank", "State Bank", "ICICI Bank", "Axis Bank", "Kotak Mahindra"]


def _gold_var(text: str) -> str:
    text = text.replace("{name}", random.choice(GOLD_NAMES))
    text = text.replace("{bank}", random.choice(GOLD_BANKS))
    text = text.replace("{url}", random.choice(GOLD_URLS))
    return text


def _make_gold_conv(texts: list, label: str, scam_type: str) -> dict:
    messages = []
    for i, text in enumerate(texts):
        sender = "scammer" if i % 2 == 0 and label == "scam" else "user"
        messages.append({
            "sender": sender,
            "text": _gold_var(text),
            "timestamp": "2026-05-01T10:00:00",
        })
    return {
        "id": str(uuid.uuid4()),
        "messages": messages,
        "label": label,
        "scam_type": scam_type,
        "language": random.choice(["hinglish", "english"]),
        "flagged_entities": [],
        "source": "gold_generator",
    }


def generate_gold_synthetic(n_per_class: int = 50) -> list:
    """Generate synthetic gold set examples — independent templates."""
    data = []
    for scam_type, templates in GOLD_TEMPLATES.items():
        label = "legitimate" if scam_type == "legitimate" else "scam"
        for _ in range(n_per_class):
            opener = random.choice(templates)
            texts = [opener]
            if label == "scam" and random.random() < 0.6:
                texts.append(random.choice(templates))
            if label == "scam":
                user_reply = random.choice([
                    "Ok kar raha hu", "Theek hai", "Done",
                    "Main ye nahi karunga", "Ye scam hai", "Bank ko call karta hu",
                ])
            else:
                user_reply = random.choice([
                    "Ok", "Done", "Theek hai", "Thanks", "Haan", "Will do",
                ])
            texts.append(user_reply)
            data.append(_make_gold_conv(texts, label, scam_type))
    random.shuffle(data)
    return data


def main():
    print("Generating independent gold set synthetic examples...")
    data = generate_gold_synthetic(n_per_class=50)
    print(f"Generated {len(data)} synthetic gold examples")

    from collections import Counter
    labels = Counter(d["label"] for d in data)
    scam_types = Counter(d["scam_type"] for d in data)
    print(f"Labels: {dict(labels)}")
    print(f"Scam types: {dict(scam_types)}")

    output_dir = os.path.join(os.path.dirname(__file__), "..", "data")
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, "gold_set.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"\nGold set saved to {output_path}")
    print("NOTE: For production, add ~1400 real scam-SMS examples + ~200 adversarial edge cases.")


if __name__ == "__main__":
    main()
