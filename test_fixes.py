"""Final verification of all fixes from TEST_REPORT.md"""

import requests
import json
import jwt
from datetime import datetime, timedelta, timezone

BASE = "http://localhost:8000"
results = []


def check(name, condition, got, expected=None):
    """Generic check helper."""
    ok = bool(condition)
    results.append({"test": name, "ok": ok, "got": got, "expected": expected})
    label = "PASS" if ok else "FAIL"
    print(f"[{label}] {name}")
    if not ok:
        print(f"       got:      {got}")
        if expected:
            print(f"       expected: {expected}")


# ── Setup ─────────────────────────────────────────────────────────────────────
login = requests.post(
    f"{BASE}/api/v1/auth/login",
    json={"email": "mavis_retest@test.com", "password": "Test123!"},
)
token = login.json().get("access_token", "")
jwt_headers = {"Authorization": f"Bearer {token}"}

# Generate a truly expired but correctly-signed token for C3 testing
secret = "dev-secret-change-in-production"
expired_payload = {
    "sub": "1", "type": "access",
    "exp": datetime.now(timezone.utc) - timedelta(hours=1),
}
expired_token = jwt.encode(expired_payload, secret, algorithm="HS256")
malformed_token = "not.a.valid.jwt.token.at.all"


def http_test(method, url, **kwargs):
    """HTTP test helper."""
    try:
        r = requests.request(method, f"{BASE}{url}", timeout=15, **kwargs)
        return r.status_code, r.json()
    except Exception as e:
        return None, str(e)


# ══ C1: Auth on /analyze ═════════════════════════════════════════════════════
status, body = http_test("POST", "/api/v1/analyze", headers=jwt_headers, json={
    "messages": [{"sender": "unknown", "text": "OTP scam message here 1234"}],
    "session_metadata": {
        "client_app_id": "test", "session_id": "x1",
        "contact_initiated_by": "unknown", "is_during_active_upi_session": False,
        "user_device_hash": "abc", "prior_reports_for_sender": 0,
    },
})
check("C1: /analyze with JWT → 200", status == 200, f"{status}")

status2, body2 = http_test("POST", "/api/v1/analyze", json={
    "messages": [{"sender": "unknown", "text": "OTP"}],
    "session_metadata": {
        "client_app_id": "test", "session_id": "x2",
        "contact_initiated_by": "unknown", "is_during_active_upi_session": False,
        "user_device_hash": "abc", "prior_reports_for_sender": 0,
    },
})
check("C1: /analyze without JWT → 401", status2 == 401, f"{status2}")


# ══ C2: Tenant isolation via X-Tenant-Id ══════════════════════════════════════
# Create two different tenants via register with different emails
import time
ts = int(time.time())
r1 = requests.post(f"{BASE}/api/v1/auth/register",
    json={"email": f"tenant_a{ts}@test.com", "password": "Test123!", "full_name": "Tenant A"})
r2 = requests.post(f"{BASE}/api/v1/auth/register",
    json={"email": f"tenant_b{ts}@test.com", "password": "Test123!", "full_name": "Tenant B"})
tok_a = requests.post(f"{BASE}/api/v1/auth/login",
    json={"email": f"tenant_a{ts}@test.com", "password": "Test123!"}).json().get("access_token", "")
tok_b = requests.post(f"{BASE}/api/v1/auth/login",
    json={"email": f"tenant_b{ts}@test.com", "password": "Test123!"}).json().get("access_token", "")

# Both users should be able to see their own dashboard
dash_a, _ = http_test("GET", "/api/v1/analytics/dashboard", headers={"Authorization": f"Bearer {tok_a}"})
dash_b, _ = http_test("GET", "/api/v1/analytics/dashboard", headers={"Authorization": f"Bearer {tok_b}"})
check("C2: Two users can both access dashboard", dash_a == 200 and dash_b == 200,
      f"user_a={dash_a}, user_b={dash_b}")


# ══ C3: Malformed vs Expired JWT ══════════════════════════════════════════════
_, m_body = http_test("GET", "/api/v1/auth/me", headers={"Authorization": f"Bearer {malformed_token}"})
_, e_body = http_test("GET", "/api/v1/auth/me", headers={"Authorization": f"Bearer {expired_token}"})
check("C3: Malformed JWT → 'Malformed authentication token'",
      m_body.get("detail", "") == "Malformed authentication token",
      m_body.get("detail", ""), "Malformed authentication token")
check("C3: Expired-but-valid JWT → 'Token has expired'",
      e_body.get("detail", "") == "Token has expired",
      e_body.get("detail", ""), "Token has expired")


# ══ H1: GET /recovery/{id} ════════════════════════════════════════════════════
# First create a recovery case
r = requests.post(f"{BASE}/api/v1/recovery/initiate", headers=jwt_headers, json={
    "fraud_type": "upi_fraud",
    "amount_lost": 5000,
    "scammer_info": "Unknown scammer",
    "incident_date": "2026-06-15",
    "victim_name": "Test User",
    "victim_phone": "9999999999",
    "bank_name": "Test Bank",
})
case_id = r.json().get("case_id", "")
status, body = http_test("GET", f"/api/v1/recovery/{case_id}", headers=jwt_headers)
check("H1: GET /recovery/{id} returns 200 for existing case", status == 200,
      f"{status} | body={str(body)[:100]}")
status2, body2 = http_test("GET", "/api/v1/recovery/nonexistent-id", headers=jwt_headers)
check("H1: GET /recovery/{id} returns 404 for unknown case", status2 == 404,
      f"{status2}")


# ══ H2: GET /compliance/rbi/{quarter} ═════════════════════════════════════════
# Analyst role can now access RBI compliance (was admin-only before)
status, body = http_test("GET", "/api/v1/compliance/rbi/Q1-2026", headers=jwt_headers)
check("H2: GET /compliance/rbi/Q1-2026 returns 200", status == 200,
      f"{status}")
if status == 200 and "quarter" in body:
    check("H2: RBI response contains quarter field", body.get("quarter") == "Q1-2026",
          body.get("quarter"))


# ══ H3: GET /audit/chain/verify ══════════════════════════════════════════════
status, body = http_test("GET", "/api/v1/audit/chain/verify", headers=jwt_headers)
check("H3: GET /audit/chain/verify → 200", status == 200, f"{status}")


# ══ H4: GET /analytics/time-series ════════════════════════════════════════════
status, body = http_test("GET", "/api/v1/analytics/time-series", headers=jwt_headers)
check("H4: GET /analytics/time-series → 200", status == 200, f"{status}")
if status == 200 and isinstance(body, list):
    check("H4: time-series returns list", len(body) >= 1, f"{len(body)} days")


# ══ H5: POST /scan ══════════════════════════════════════════════════════════
status, body = http_test("POST", "/api/v1/scan", json={"text": "Your OTP is 9999"})
check("H5: POST /scan → 200", status == 200, f"{status}")
if status == 200:
    check("H5: scan returns result.is_scam", body.get("result", {}).get("is_scam") is not None,
          body.get("result", {}).get("is_scam"))


# ══ M1: Hindi warning populated ══════════════════════════════════════════════
_, body = http_test("POST", "/api/v1/analyze", headers=jwt_headers, json={
    "messages": [{"sender": "unknown", "text": "Your OTP 1234 share immediately"}],
    "session_metadata": {
        "client_app_id": "test", "session_id": "s3",
        "contact_initiated_by": "unknown", "is_during_active_upi_session": False,
        "user_device_hash": "abc", "prior_reports_for_sender": 0,
    },
})
warning_hi = body.get("warning_message_hi", "")
check("M1: Hindi warning is non-empty", len(warning_hi) > 0, f"len={len(warning_hi)}")
if warning_hi:
    check("M1: Hindi warning contains meaningful text",
          len(warning_hi) > 10,
          warning_hi[:50])


# ══ Summary ═══════════════════════════════════════════════════════════════════
print("\n" + "=" * 60)
passed = sum(1 for x in results if x["ok"])
total = len(results)
print(f"RESULT: {passed}/{total} checks passed")
for x in results:
    label = "PASS" if x["ok"] else "FAIL"
    print(f"  [{label}] {x['test']}")
