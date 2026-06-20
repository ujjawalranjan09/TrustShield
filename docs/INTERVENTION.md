# Intervention System

How TrustShield takes action when fraud is detected.

## Consent Model

All proactive interventions require explicit DPDP (Digital Personal Data Protection) consent from the user. The consent gate is enforced in `app/services/intervention/action_engine.py:evaluate_intervention()`.

**Consent check flow:**
1. Check `proactive_intervention_enabled` config flag
2. Verify entity risk exceeds `intervention_risk_threshold` (default 0.8)
3. Verify `consented` field is `True` in the intel event
4. If any check fails, intervention is skipped with reason logged

**Consent sources:**
- SDK integration: consent collected during app onboarding
- Web portal: consent via checkbox during report submission
- Bank API: consent flag from bank's customer verification

Without consent, the system still performs real-time blocking (which doesn't require consent as it's protective), but cannot enqueue proactive warnings or freeze transactions.

## Intervention Types and Thresholds

The `ActionEngine` maps composite risk scores to actions:

| Score Range | Action | Description |
|-------------|--------|-------------|
| 0–30 | NONE | No intervention |
| 31–50 | SOFT_WARNING | Non-blocking advisory message |
| 51–70 | HARD_BLOCK | PIN entry disabled temporarily |
| 71–85 | FREEZE_AND_REPORT | Transaction frozen, flagged for review |
| 86–100 | CRITICAL_REPORT | Blocked + reported to 1930 cybercrime |

**Special case — Coached Victim:**
If `behavioral_risk_score ≥ 0.6` AND `classifier_confidence ≥ 0.8`, the system triggers `COACHED_VICTIM_INTERVENTION` regardless of the score. This handles scenarios where a victim is being actively guided by a scammer.

**Composite score calculation:**
```
final_score = risk_score.score + int(graph_enrichment.graph_risk_score * 20)
final_score = min(100, final_score)
```

## WhatsApp Message Templates

Messages are sent via `app/services/intervention/whatsapp_sender.py` using the WhatsApp Business API.

| Action | English Template | Hindi Template |
|--------|-----------------|----------------|
| SOFT_WARNING | "Please be careful. Do not share your OTP." | "Kripya savdhan rahein. Apna OTP share na karein." |
| HARD_BLOCK | "Warning: High risk of fraud! We have disabled PIN entry temporarily." | "Chetawani: Fraud ka khatra! Humne PIN entry kuch samay ke liye block kar diya hai." |
| FREEZE_AND_REPORT | "Transaction Frozen. This session is flagged as fraudulent." | "Transaction Rok Di Gayi Hai. Yeh session fraud mana gaya hai." |
| CRITICAL_REPORT | "Critical Security Alert: Session blocked. Reported to authorities." | "Gambhirs Suraksha Chetawani: Session block kar diya gaya hai aur report kar diya gaya hai." |
| COACHED_VICTIM | "CRITICAL: We detect signs you may be coached by a scammer. Transactions frozen. Call your bank's fraud helpline immediately." | "GAMBHIR: Humko lagta hai ki aapko scammer guide kar raha hai. Transactions rok diye gaye hain. Turant bank ke fraud helpline par call karein." |

## Bank-Freeze Webhook Contract

When `FREEZE_AND_REPORT` or `CRITICAL_REPORT` is triggered, TrustShield calls the bank's freeze webhook:

```
POST {bank.freeze_webhook_url}
Content-Type: application/json
X-TrustShield-Signature: sha256={hmac-signature}

{
  "session_id": "sess-12345",
  "action": "FREEZE_AND_REPORT",
  "entity_value": "hashed-entity",
  "entity_type": "PHONE",
  "risk_score": 82,
  "risk_level": "CRITICAL",
  "scam_type": "vishing",
  "timestamp": "2025-01-15T10:30:00Z",
  "evidence": {
    "report_count": 15,
    "ring_id": "ring-abc123",
    "propagated_risk": 0.75
  }
}
```

**Response expected:**
```json
{
  "status": "accepted",
  "freeze_id": "freeze-xyz",
  "message": "Account frozen for review"
}
```

**Signature verification:** Banks verify the payload using HMAC-SHA256 with the shared webhook secret. See `docs/API_GUIDE.md` for verification code samples.

**Retry policy:** Failed webhook calls are retried 3 times with exponential backoff (1s, 5s, 25s). Failures are logged to the audit trail.
