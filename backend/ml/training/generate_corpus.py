"""Generate 100k labeled conversations for TrustShield training.

Produces diverse scam + legitimate conversations across 8 classes using
template-based generation with synonym substitution, sentence reordering,
and number/amount variation. No external API calls.

Usage:
    python -m ml.training.generate_corpus
"""

import json
import os
import random
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

TEMPLATES = {
    "otp_harvesting": {
        "scammer_opens": [
            "Sir your {bank} account mein problem aa rahi hai",
            "Hello {name}, main {bank} se bol raha hu",
            "Ma'am your account has been compromised",
            "Urgent: your {bank} account is locked",
            "Dear customer, your account needs verification",
            "I'm calling from {bank} fraud department",
            "Your ATM card is blocked. Verify to unblock",
            "Bank se call aa raha hai, account issue hai",
            "Aapka account freeze ho jayega agar verify nahi kiya",
            "RBI ne order diya hai aapka account check karne ka",
        ],
        "otp_request": [
            "Aapke phone pe OTP aayega wo mujhe batao",
            "Please share the OTP you just received",
            "OTP forward karo turant, account save hoga",
            "Jo OTP aaya hai wo 4 digit code mujhe bhejo",
            "Ek baar OTP share kar do, phir band ho jayega",
            "Verification ke liye OTP chahiye",
            "OTP batana padega warna account block ho jayega",
            "Quick — OTP aaya hoga, number batao",
            "Your one-time password is needed to complete verification",
            "Send me the code from your SMS immediately",
        ],
        "urgency": [
            "Sirf 2 minute ka kaam hai, phir aapka account safe hai",
            "Jaldi karo warna account permanently block ho jayega",
            "Abhi karo, 5 minute mein band ho jayega ye",
            "Time kam hai, jaldi OTP share karo",
            "This is your last chance to verify",
            "Agar abhi nahi kiya toh FIR filed ho jayega",
        ],
        "legit_replies": [
            "Ok sir batao kya karna hai",
            "Haan OTP aa raha hai, batata hu",
            "Theek hai, code share kar raha hu",
            "Done, OTP bhej diya",
            "Ok sending now",
            "Code receive hua hai, forward kar raha hu",
        ],
        "user_replies": [
            "Main koi OTP share nahi karunga",
            "Bank wale OTP kabhi share nahi karte",
            "Ye scam lag raha hai, main report karunga",
            "I won't share my OTP with anyone",
            "This is a scam. Don't call me again.",
            "Main bank ko directly call karunga",
        ],
    },
    "vishing": {
        "scammer_opens": [
            "Sir your account has {issue}",
            "Ma'am there's suspicious activity on your {bank} account",
            "Urgent security alert for account ending in {digits}",
            "{bank} security department here, your account is at risk",
            "Your account will be frozen within 24 hours",
            "RBI has flagged your account for review",
            "Your KYC is expired, account will be deactivated",
            "ATM card expiry detected, please verify immediately",
        ],
        "pressure": [
            "Aapko abhi verify karna padega, nahi toh account block",
            "Sir please cooperate, ye bahut serious matter hai",
            "Time nahi hai, abhi karna hoga",
            "If you don't comply, police will be notified",
            "This is your final warning from the bank",
            "Your account balance will be transferred to RBI if not verified",
            "Compliance department ne order diya hai",
        ],
        "otp_request": [
            "OTP aayega, wo share karna padega verification ke liye",
            "Please share the OTP for KYC update",
            "Verification code bhejo, account activate hoga",
            "Ek baar OTP de do, sab sorted ho jayega",
        ],
        "legit_replies": [
            "Ok sir, OTP share kar raha hu",
            "Theek hai, kya karna hai batao",
            "Haan batao, kya problem hai",
            "Ok I'll verify now",
        ],
        "user_replies": [
            "Main bank ki official line pe call karunga",
            "Aapka number verify karta hu pehle",
            "Ye scam hai, main 1930 pe report karunga",
            "Don't call me again, I'm reporting this",
            "I'll visit my branch directly",
        ],
    },
    "remote_access": {
        "scammer_opens": [
            "Sir your phone has virus, need to fix it remotely",
            "Ma'am your device is compromised, install AnyDesk for support",
            "Bank technical support here, need to access your screen",
            "Your phone needs emergency security update via remote",
            "Download TeamViewer for instant account recovery",
            "We need to check your device for malware",
            "Your phone is being tracked, let us help remotely",
        ],
        "app_request": [
            "AnyDesk download karo, main fix kar dunga",
            "Play Store se TeamViewer install karo",
            "Ye app download karo: anydesk.com/support",
            "Remote access app chahiye for troubleshooting",
            "Screen share karo, problem solve ho jayegi",
            "Download QuickSupport app from Play Store",
            "Please install remote support tool immediately",
        ],
        "reassurance": [
            "Sirf 2 minute lagega, phir account safe ho jayega",
            "Kuch nahi hoga, ye bank ka official process hai",
            "Don't worry, this is standard procedure",
            "Trust me, this is how banks handle fraud now",
            "Main bank ka authorized technician hu",
        ],
        "legit_replies": [
            "Ok app install kar raha hu",
            "Download kar liya, kya karna hai",
            "AnyDesk khol diya, code batao",
            "Ok opening the app now",
        ],
        "user_replies": [
            "Main koi app install nahi karunga",
            "AnyDesk pe trust nahi karta, ye scam hai",
            "Main bank branch jaunga personally",
            "I'm not installing anything. Goodbye.",
            "Ye clearly scam hai, police ko batata hu",
        ],
    },
    "refund_scam": {
        "scammer_opens": [
            "Sir aapka {amount} ka refund approved ho gaya",
            "Your refund of Rs {amount} is ready for transfer",
            "Ma'am Rs {amount} refund milega, scan karna hoga",
            "Failed transaction ka refund aa gaya hai",
            "Your cashback of {amount} is pending. Scan to receive.",
            "Refund process complete, QR scan karein",
        ],
        "qr_request": [
            "Ye QR code scan karo, paisa turant aa jayega",
            "Payment receive karne ke liye ye scan karo",
            "QR scan karo with PIN, refund credit ho jayega",
            "Scan this QR and enter your UPI PIN to receive refund",
            "Refund ke liye ye link open karo aur PIN daalo",
            "QR code bhej raha hu, scan karo with PIN",
        ],
        "reassurance": [
            "Ye normal process hai, kuch nahi hoga",
            "Trust me, paisa aapka hi rahega",
            "100% safe hai, bank ka official QR hai",
            "This is the standard refund procedure",
            "Don't worry, your money is safe",
        ],
        "legit_replies": [
            "Ok scan kar raha hu",
            "QR receive hua, kar raha hu",
            "Ok PIN daal raha hu",
            "Done, refund receive ho jayega kya",
        ],
        "user_replies": [
            "Main QR scan nahi karunga, ye scam hai",
            "UPI pe kabhi PIN mat daalo QR scan pe",
            "Refund seedha account mein aata hai, ye fake hai",
            "I know you can't receive money by scanning QR. Scam.",
            "Main NPCI ko report karunga",
        ],
    },
    "fake_support": {
        "scammer_opens": [
            "Hello, I'm from {bank} customer support",
            "Sir your complaint #REF{digits} is being processed",
            "We're calling about your recent transaction dispute",
            "{bank} support team here, resolving your issue",
            "Ma'am your KYC document is pending, we need to verify",
            "Customer care se bol raha hu, account issue hai",
        ],
        "info_request": [
            "Your account number and IFSC share karo for refund",
            "Please verify your last 4 digits of card number",
            "Card details chahiye for processing refund",
            "OTP share karo for verification",
            "Your UPI PIN temporarily share karo for verification",
            "Date of birth and mother's name batao for verification",
        ],
        "reassurance": [
            "Ye bank ka official process hai",
            "Don't worry, your data is secure with us",
            "Sirf verification ke liye chahiye",
            "Trust me, ye procedure hai",
            "We handle thousands of cases daily",
        ],
        "legit_replies": [
            "Ok details share kar raha hu",
            "Theek hai, card number hai: XXXX",
            "Account number bata raha hu",
            "Ok OTP bhej diya",
        ],
        "user_replies": [
            "Bank kabhi ye details phone pe nahi mangta",
            "Main khud branch mein aunga",
            "Ye details share nahi karunga, scam hai",
            "I'll call the official bank number myself",
            "This is fraud, I'm reporting to cybercrime",
        ],
    },
    "phishing": {
        "scammer_opens": [
            "Click this link to verify your account: {url}",
            "Your account needs urgent verification at {url}",
            "Update KYC at this link or account will close: {url}",
            "URGENT: Suspicious login detected. Secure here: {url}",
            "Your prize of Rs {amount} is waiting. Claim at: {url}",
            "Bank website pe jaake verify karo: {url}",
        ],
        "link_content": [
            "http://secure-{bank}-verify.com/kyc",
            "http://{bank}-update.in/urgent",
            "http://account-verify.net/login",
            "http://prize-claim.in/win{amount}",
            "http://banking-secure.com/verify",
            "http://kyc-update.co.in/submit",
        ],
        "reassurance": [
            "Ye bank ka official link hai",
            "Link sirf verification ke liye hai",
            "Sirf 2 minute lagega, account safe ho jayega",
            "This is the bank's official portal",
            "Don't ignore this or your account will be blocked",
        ],
        "legit_replies": [
            "Ok link open kar raha hu",
            "Verify kar raha hu abhi",
            "Link click kiya, details bhar raha hu",
            "Done, verify ho jayega kya",
        ],
        "user_replies": [
            "Main ye link open nahi karunga",
            "Ye phishing link hai, block karta hu",
            "Bank official URL alag hota hai, ye fake hai",
            "I never click unknown links. This is a scam.",
            "Main cybercrime.gov.in pe report karunga",
        ],
    },
    "sim_swap": {
        "scammer_opens": [
            "Sir your SIM has been deactivated, we need to reactivate",
            "Your new SIM is ready, please confirm the OTP",
            "SIM swap request received, verify to complete",
            "Network issue ke liye naya SIM activate karna hoga",
            "Your SIM card is expired, new one needs verification",
            "Telecom department: SIM replacement pending",
        ],
        "otp_request": [
            "Naya SIM pe OTP aayega, wo forward karo",
            "New SIM activate karne ke liye OTP chahiye",
            "Please share the activation code for new SIM",
            "SIM port ke liye OTP share karo",
            "Jo OTP aaya hai wo number batao for verification",
        ],
        "reassurance": [
            "Ye telecom ka official process hai",
            "SIM activate hone pe sab same rahega",
            "Trust me, this is standard procedure",
            "Sirf verification ke liye OTP chahiye",
            "Don't worry, your number won't change",
        ],
        "legit_replies": [
            "Ok OTP forward kar raha hu",
            "Code share kar raha hu",
            "Haan OTP aaya hai, bata raha hu",
            "Done, activate ho jayega kya",
        ],
        "user_replies": [
            "Main koi OTP share nahi karunga",
            "SIM swap scam hai ye, report karta hu",
            "Telecom ko directly call karunga",
            "I know SIM swap fraud. Don't contact me again.",
            "Main nearest store pe jaunga personally",
        ],
    },
    "legitimate": {
        "templates": [
            [{"sender": "user", "text": "{name} kal kitne baje aana hai?"},
             {"sender": "friend", "text": "10 baje aa jana, meeting hai."},
             {"sender": "user", "text": "Ok see you."}],
            [{"sender": "user", "text": "Report bhej diya kya?"},
             {"sender": "colleague", "text": "Haan kal bhej diya. Check kar lo."},
             {"sender": "user", "text": "Ok dekh raha hu."}],
            [{"sender": "user", "text": "Payment received, thanks!"},
             {"sender": "seller", "text": "Welcome! Delivery 3 din mein ho jayegi."}],
            [{"sender": "user", "text": "Meeting cancel ho gayi kya?"},
             {"sender": "colleague", "text": "Nahi hai, 3 PM hi hai. Don't be late."},
             {"sender": "user", "text": "Ok I'll be there."}],
            [{"sender": "user", "text": "Package kab tak aayega?"},
             {"sender": "seller", "text": "Kal deliver ho jayega. Track kar sakte ho app pe."}],
            [{"sender": "user", "text": "Documents bhej diye email pe"},
             {"sender": "hr", "text": "Received. Will review and get back."},
             {"sender": "user", "text": "Thanks!"}],
            [{"sender": "user", "text": "Lunch at 1?"},
             {"sender": "friend", "text": "12:30 pe chalte hain. Cafeteria mein?"},
             {"sender": "user", "text": "Done!"}],
            [{"sender": "user", "text": "Client call hai 4 PM. Ready ho?"},
             {"sender": "colleague", "text": "Haan, presentation ready hai."}],
            [{"sender": "user", "text": "Birthday party kal night?"},
             {"sender": "friend", "text": "Haan 8 PM pe aana. Cake aa jayega."},
             {"sender": "user", "text": "Sure! Gift le aunga."}],
            [{"sender": "user", "text": "Cab book kar di hai. 5 min mein aa jayegi."},
             {"sender": "friend", "text": "Ok main bhi nikal raha hu."}],
            [{"sender": "user", "text": "Grocery list share kar di WhatsApp pe"},
             {"sender": "spouse", "text": "Ok, evening mein le aaungi."}],
            [{"sender": "user", "text": "Flight confirm ho gayi! Mumbai ja raha hu"},
             {"sender": "friend", "text": "Nice! Kab hai?"},
             {"sender": "user", "text": "Next Friday. 3 din ka trip."}],
            [{"sender": "user", "text": "Auto nahi mil raha. Tu aa jayega kya?"},
             {"sender": "friend", "text": "10 min mein pahunch raha hu."}],
            [{"sender": "user", "text": "Gym jana hai aaj. Saath chalein?"},
             {"sender": "friend", "text": "Haan 6 PM pe milte hain."}],
            [{"sender": "user", "text": "Assignment submit kar diya"},
             {"sender": "teacher", "text": "Noted. Marks next week aa jayenge."}],
            [{"sender": "user", "text": "Doctor ka appointment kal hai kya?"},
             {"sender": "spouse", "text": "Haan 11 AM. Don't forget to carry reports."}],
            [{"sender": "user", "text": "Movie dekhne chalte hain weekend pe"},
             {"sender": "friend", "text": "Kaunsi? Trailer accha laga naya wala."},
             {"sender": "user", "text": "Haan wahi. Book karta hu tickets."}],
            [{"sender": "user", "text": "Electricity bill aaya hai kya?"},
             {"sender": "spouse", "text": "Haan 2400 hai. Pay kar du?"},
             {"sender": "user", "text": "Haan kar de, thanks."}],
            [{"sender": "user", "text": "Office ka Wi-Fi password kya hai?"},
             {"sender": "colleague", "text": "TrustShield-Guest hai. Password: ts2026."}],
            [{"sender": "user", "text": "Project deadline extend ho gayi!"},
             {"sender": "colleague", "text": "Accha hai! Abhi time hai properly karne ka."}],
            [{"sender": "user", "text": "Salary aa gayi kya?"},
             {"sender": "friend", "text": "Haan kal aayi. Check kar."}],
            [{"sender": "user", "text": "Car ka insurance renew karna hai"},
             {"sender": "spouse", "text": "Online kar le. Discount mil raha hai."}],
            [{"sender": "user", "text": "Weekend pe trek chalte hain?"},
             {"sender": "friend", "text": "Haan! Lonavala ka plan banate hain."}],
            [{"sender": "user", "text": "Interview kal hai. Koi tips?"},
             {"sender": "friend", "text": "Be confident. Company research kar le pehle."}],
            [{"sender": "user", "text": "Ghar ka address bhej do delivery ke liye"},
             {"sender": "friend", "text": "Flat 302, Green Valley, Andheri West."}],
            [{"sender": "user", "text": "New phone konsa le raha hai?"},
             {"sender": "friend", "text": "Pixel 9 soch raha hu. Camera accha hai."}],
            [{"sender": "user", "text": "Tiffin bhej diya hai. 1 PM tak aa jayega"},
             {"sender": "spouse", "text": "Ok. Thanks!"}],
            [{"sender": "user", "text": "College ka result aa gaya"},
             {"sender": "friend", "text": "Kaisa hua?"},
             {"sender": "user", "text": "First class aa gayi!"}],
            [{"sender": "user", "text": "Flat ka rent bhej diya"},
             {"sender": "landlord", "text": "Received. Thanks."}],
            [{"sender": "user", "text": "Team dinner kal hai. Confirm karo"},
             {"sender": "colleague", "text": "Confirmed. 8 PM at the usual place."}],
        ],
    },
}

SYNONYMS = {
    "bank": ["HDFC", "SBI", "ICICI", "Axis", "Kotak", "PNB", "BOB", "Canara"],
    "name": ["Rahul", "Priya", "Amit", "Sneha", "Vikram", "Pooja", "Ravi", "Neha", "Arun", "Deepa"],
    "issue": [
        "unauthorized transaction detected",
        "suspicious login from unknown device",
        "failed KYC verification",
        "card cloned at ATM",
        "multiple failed OTP attempts",
        "account flagged by RBI",
    ],
    "digits": ["4521", "7832", "1098", "3456", "8901", "2345", "6789", "5678"],
    "amount": ["5000", "10000", "15000", "25000", "50000", "75000", "100000", "200000"],
    "url": [
        "secure-verify.com", "bank-update.in", "kyc-verify.net",
        "account-recovery.co.in", "prize-claim.in", "banking-secure.com",
    ],
}


def _var(text: str) -> str:
    for key, options in SYNONYMS.items():
        if f"{{{key}}}" in text:
            text = text.replace(f"{{{key}}}", random.choice(options))
    return text


def _generate_scam_conversation(scam_type: str) -> list:
    templates = TEMPLATES[scam_type]
    messages = [{"sender": "scammer", "text": _var(random.choice(templates["scammer_opens"]))}]

    follow_up_keys = [k for k in templates if k not in ("scammer_opens", "legit_replies", "user_replies")]
    for _ in range(random.randint(1, 3)):
        key = random.choice(follow_up_keys)
        msg = _var(random.choice(templates[key]))
        messages.append({"sender": "scammer", "text": msg})

    if random.random() < 0.5:
        reply = random.choice(templates["legit_replies"])
    else:
        reply = random.choice(templates["user_replies"])
    messages.append({"sender": "user", "text": _var(reply)})

    if random.random() < 0.4 and follow_up_keys:
        key = random.choice(follow_up_keys)
        messages.append({"sender": "scammer", "text": _var(random.choice(templates[key]))})

    return messages


def _generate_legitimate_conversation() -> list:
    template = random.choice(TEMPLATES["legitimate"]["templates"])
    return [{"sender": msg["sender"], "text": _var(msg["text"])} for msg in template]


def _make_conversation(messages: list, label: str, scam_type: str = "none") -> dict:
    return {
        "id": str(uuid.uuid4()),
        "messages": [{**msg, "timestamp": "2026-05-01T10:00:00"} for msg in messages],
        "label": label,
        "scam_type": scam_type,
        "language": random.choice(["hinglish", "english", "hindi"]),
        "flagged_entities": [],
    }


def generate_corpus(target_per_class: int = 12500) -> list:
    all_data = []
    scam_types = ["otp_harvesting", "vishing", "remote_access", "refund_scam", "fake_support", "phishing", "sim_swap"]

    for scam_type in scam_types:
        for _ in range(target_per_class):
            messages = _generate_scam_conversation(scam_type)
            all_data.append(_make_conversation(messages, "scam", scam_type))

    legit_target = target_per_class + 1500
    for _ in range(legit_target):
        messages = _generate_legitimate_conversation()
        all_data.append(_make_conversation(messages, "legitimate", "none"))

    random.shuffle(all_data)
    return all_data


def create_splits(data: list, output_dir: str):
    os.makedirs(output_dir, exist_ok=True)
    random.shuffle(data)
    n = len(data)
    splits = {
        "train.json": data[:int(n * 0.80)],
        "val.json": data[int(n * 0.80):int(n * 0.90)],
        "calibration.json": data[int(n * 0.90):int(n * 0.95)],
        "test.json": data[int(n * 0.95):],
    }
    for filename, split_data in splits.items():
        path = os.path.join(output_dir, filename)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(split_data, f, indent=2, ensure_ascii=False)
        print(f"  {filename}: {len(split_data)} conversations")
    return splits


def main():
    print("Generating 100k conversation corpus...")
    data = generate_corpus(target_per_class=12500)
    print(f"Total generated: {len(data)}")

    from collections import Counter
    labels = Counter(d["label"] for d in data)
    scam_types = Counter(d["scam_type"] for d in data)
    print(f"Labels: {dict(labels)}")
    print(f"Scam types: {dict(scam_types)}")

    output_dir = os.path.join(os.path.dirname(__file__), "..", "data")
    print(f"\nCreating splits in {output_dir}...")
    create_splits(data, output_dir)
    print("\nDone!")


if __name__ == "__main__":
    main()
