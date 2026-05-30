from typing import Optional
from pydantic import BaseModel
from app.schemas.risk import RiskScore, ActionCode

class GraphEnrichment(BaseModel):
    graph_risk_score: float
    connected_blacklisted_entities: int

class InterventionDecision(BaseModel):
    action: ActionCode
    warning_message_en: Optional[str] = None
    warning_message_hi: Optional[str] = None
    reason: str

class ActionEngine:
    def decide(self, risk_score: RiskScore, graph_enrichment: GraphEnrichment) -> InterventionDecision:

        # Merge graph risk
        final_score = risk_score.score + int(graph_enrichment.graph_risk_score * 20)
        final_score = min(100, final_score)

        if final_score <= 30:
            return InterventionDecision(
                action=ActionCode.NONE,
                reason="Low risk detected."
            )
        elif final_score <= 50:
            return InterventionDecision(
                action=ActionCode.SOFT_WARNING,
                warning_message_en="Please be careful. Do not share your OTP.",
                warning_message_hi="Kripya savdhan rahein. Apna OTP share na karein.",
                reason="Medium risk detected. Suspicious keywords found."
            )
        elif final_score <= 70:
            return InterventionDecision(
                action=ActionCode.HARD_BLOCK,
                warning_message_en="Warning: High risk of fraud! We have disabled PIN entry temporarily.",
                warning_message_hi="Chetawani: Fraud ka khatra! Humne PIN entry kuch samay ke liye block kar diya hai.",
                reason="High risk detected. Known scam patterns or risky entities present."
            )
        elif final_score <= 85:
            return InterventionDecision(
                action=ActionCode.FREEZE_AND_REPORT,
                warning_message_en="Transaction Frozen. This session is flagged as fraudulent.",
                warning_message_hi="Transaction Rok Di Gayi Hai. Yeh session fraud mana gaya hai.",
                reason="Very high risk detected. Initiating transaction freeze."
            )
        else:
            return InterventionDecision(
                action=ActionCode.CRITICAL_REPORT,
                warning_message_en="Critical Security Alert: Session blocked. Reported to authorities.",
                warning_message_hi="Gambhirs Suraksha Chetawani: Session block kar diya gaya hai aur report kar diya gaya hai.",
                reason="Critical risk. Known scammer entities detected. Calling 1930 API."
            )
