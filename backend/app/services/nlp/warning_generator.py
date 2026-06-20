"""Adaptive bilingual warning generator.

Template-based for v1 (EN + HI). LLM integration optional.
"""

import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

WARNINGS = {
    "otp_harvesting": {
        "en": {
            "critical": "CRITICAL: This message is attempting to steal your OTP. Never share your One-Time Password with anyone, even if they claim to be from your bank. Block the sender immediately.",
            "high": "WARNING: This message contains suspicious OTP-related content. Do not share any verification codes.",
            "medium": "CAUTION: This message mentions verification codes. Be careful about sharing OTPs.",
        },
        "hi": {
            "critical": "GAMBHIR: Yeh sandesh aapka OTP chori karne ki koshish kar raha hai. Kabhi bhi apna OTP kisi ko na bhein, chahe woh bank ka aadmi bhi ho. Turant bhejne wale ko block karein.",
            "high": "CHETAWANI: Is sandesh mein OTP se sambandhit sandehjanak samagri hai. Koi bhi verification code share na karein.",
            "medium": "SAVDHAN: Is sandesh mein verification codes ka zikr hai. OTP share karne mein saavdhan rahein.",
        },
    },
    "vishing": {
        "en": {
            "critical": "CRITICAL: This is a vishing (phone scam) attempt. The scammer is pretending to be from your bank to steal sensitive information. Do not share any personal or financial details.",
            "high": "WARNING: This message shows signs of a phone scam. Do not provide account details or verification codes.",
            "medium": "CAUTION: Suspicious banking-related content detected. Verify the sender independently.",
        },
        "hi": {
            "critical": "GAMBHIR: Yeh vishing (phone scam) hai. Scammer bank ka aadmi bankar sensitive jaankari chori karne ki koshish kar raha hai. Koi bhi vyaktigat ya vittiy jaankari na dein.",
            "high": "CHETAWANI: Is sandesh mein phone scam ke lakshan hain. Account details ya verification codes na dein.",
            "medium": "SAVDHAN: Sandehjanak banking samagri mili hai. Bhejne wale ko swayam verify karein.",
        },
    },
    "remote_access": {
        "en": {
            "critical": "CRITICAL: This message asks you to install remote access software (AnyDesk/TeamViewer). NEVER install such apps on the request of a stranger — they will take full control of your device and steal your money.",
            "high": "WARNING: Remote access tool detected. Do not install AnyDesk, TeamViewer, or similar apps as requested.",
            "medium": "CAUTION: Message mentions remote access tools. Be extremely cautious.",
        },
        "hi": {
            "critical": "GAMBHIR: Yeh sandesh aapse remote access software (AnyDesk/TeamViewer) install karne ko keh raha hai. PARAYO SE AISE APPS KABHI NA INSTALL KAREIN — woh aapke device ka poora control le lenge aur aapka paisa chura lenge.",
            "high": "CHETAWANI: Remote access tool mila hai. AnyDesk, TeamViewer jaise apps na install karein.",
            "medium": "SAVDHAN: Sandesh mein remote access tools ka zikr hai. Bahut saavdhan rahein.",
        },
    },
    "refund_scam": {
        "en": {
            "critical": "CRITICAL: This is a QR code / refund scam. The scammer wants you to scan a QR code and enter your UPI PIN. NEVER enter your PIN to receive money — you will LOSE money instead.",
            "high": "WARNING: Suspicious refund offer detected. Do not scan QR codes or enter your UPI PIN.",
            "medium": "CAUTION: Message mentions refunds or QR codes. Verify independently before acting.",
        },
        "hi": {
            "critical": "GAMBHIR: Yeh QR code / refund dhoka hai. Scammer aapse QR code scan karwakar UPI PIN dalwana chahta hai. PAISA PAANE KE LIYE KABHI PIN NA DALEIN — aapka paisa kat jayega.",
            "high": "CHETAWANI: Sandehjanak refund offer mili hai. QR code na scan karein aur UPI PIN na daalein.",
            "medium": "SAVDHAN: Sandesh mein refunds ya QR codes ka zikr hai. Karwai se pehle swayam verify karein.",
        },
    },
    "fake_support": {
        "en": {
            "critical": "CRITICAL: This is a fake customer support scam. Real banks never ask for your card details, OTP, or PIN over phone/chat. Hang up and call your bank's official number.",
            "high": "WARNING: Suspicious support message. Do not share account details with unsolicited contacts.",
            "medium": "CAUTION: Claims to be from customer support. Verify by calling the official bank number.",
        },
        "hi": {
            "critical": "GAMBHIR: Yeh nakli customer support dhoka hai. Asli bank kabhi phone/chat par card details, OTP ya PIN nahi mangta. Phone rakhein aur bank ke official number par call karein.",
            "high": "CHETAWANI: Sandehjanak support sandesh. Anjaan logon ko account details na dein.",
            "medium": "SAVDHAN: Customer support ka daava hai. Official bank number par call karke verify karein.",
        },
    },
    "phishing": {
        "en": {
            "critical": "CRITICAL: This is a phishing link. Do NOT click any links in this message. Real banks never ask you to verify accounts via SMS links.",
            "high": "WARNING: Suspicious link detected. Do not click or enter any information.",
            "medium": "CAUTION: Message contains a link. Verify the URL before clicking.",
        },
        "hi": {
            "critical": "GAMBHIR: Yeh phishing link hai. Is sandesh mein koi bhi link KABHI NA CLICK KAREIN. Asli bank SMS link par account verify nahi karwata.",
            "high": "CHETAWANI: Sandehjanak link mila hai. Link par click na karein ya koi jaankari na dein.",
            "medium": "SAVDHAN: Sandesh mein link hai. Click karne se pehle URL verify karein.",
        },
    },
    "sim_swap": {
        "en": {
            "critical": "CRITICAL: This is a SIM swap scam. Do NOT share any OTP or activation code. Your phone number could be hijacked.",
            "high": "WARNING: SIM-related scam detected. Do not forward any codes.",
            "medium": "CAUTION: Message mentions SIM activation. Be cautious.",
        },
        "hi": {
            "critical": "GAMBHIR: Yeh SIM swap dhoka hai. Koi bhi OTP ya activation code SHARE NA KAREIN. Aapka phone number hijack ho sakta hai.",
            "high": "CHETAWANI: SIM sambandhit dhoka mila hai. Koi code forward na karein.",
            "medium": "SAVDHAN: Sandesh mein SIM activation ka zikr hai. Saavdhan rahein.",
        },
    },
}

LEGITIMATE = {
    "en": "This message appears to be legitimate. However, always stay vigilant about sharing personal information.",
    "hi": "Yeh sandesh sahi lagta hai. Lekin hamesha apni personal jaankari share karne mein saavdhan rahein.",
}


class WarningGenerator:
    def generate(
        self,
        scam_type: str,
        risk_score: int,
        entities: Optional[List] = None,
        locale: str = "en",
    ) -> Dict[str, str]:
        """Generate bilingual warning messages.

        Always populates both warning_en and warning_hi, using the appropriate
        locale's warning and falling back to the other locale's version if unavailable.
        """
        risk_level = "critical" if risk_score >= 70 else "high" if risk_score >= 40 else "medium"

        scam_warnings = WARNINGS.get(scam_type, {})

        # Get EN warning (with HI fallback)
        warning_en = (
            scam_warnings.get("en", {}).get(risk_level, "")
            or scam_warnings.get("hi", {}).get(risk_level, "")
            or LEGITIMATE["en"]
        )

        # Get HI warning (with EN fallback)
        warning_hi = (
            scam_warnings.get("hi", {}).get(risk_level, "")
            or scam_warnings.get("en", {}).get(risk_level, "")
            or LEGITIMATE["hi"]
        )

        # Add entity-specific context
        if entities:
            entity_names = [getattr(e, "entity_type", str(e)) for e in entities[:3]]
            entity_context_en = f" Detected: {', '.join(entity_names)}."
            entity_context_hi = f" Mile hue entities: {', '.join(entity_names)}."
            warning_en += entity_context_en
            warning_hi += entity_context_hi

        return {
            "warning_en": warning_en,
            "warning_hi": warning_hi,
        }
