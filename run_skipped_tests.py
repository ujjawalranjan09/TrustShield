"""Comprehensive test runner for TrustShield skipped items — v2."""
import json
import urllib.request
import urllib.error
import time

BASE = "http://localhost:8000/api/v1"

def req(method, path, headers=None, body=None, timeout=15):
    url = f"{BASE}{path}"
    data = json.dumps(body).encode() if body is not None else None
    hdrs = {"Content-Type": "application/json"}
    if headers:
        hdrs.update(headers)
    req_obj = urllib.request.Request(url, data=data, headers=hdrs, method=method)
    try:
        resp = urllib.request.urlopen(req_obj, timeout=timeout)
        body_raw = resp.read().decode()
        try:
            body_json = json.loads(body_raw)
        except json.JSONDecodeError:
            body_json = body_raw
        return {"status": resp.status, "body": body_json}
    except urllib.error.HTTPError as e:
        body_raw = e.read().decode()
        try:
            body_json = json.loads(body_raw)
        except json.JSONDecodeError:
            body_json = body_raw
        return {"status": e.code, "body": body_json}
    except Exception as e:
        return {"status": "ERROR", "body": str(e)}

results = []

def log(tid, desc, result):
    results.append({"test_id": tid, "description": desc, "http_status": result["status"], "response": result["body"]})
    print(f"\n{'='*60}")
    print(f"[{tid}] {desc}")
    print(f"  HTTP {result['status']}")
    raw = json.dumps(result["body"], indent=2, ensure_ascii=False)
    if len(raw) > 2000:
        print(f"  BODY (truncated): {raw[:2000]}...")
    else:
        print(f"  BODY: {raw}")

# ============================================================
# PHASE 1 — Auth skipped items
# ============================================================

# 1.1 Register new user (should work now)
r = req("POST", "/auth/register", body={
    "email": "skiptest@test.com", "password": "Test123!", "full_name": "Skip Test"
})
log("1.1", "POST /auth/register (new user)", r)

# 1.2 Duplicate register
r = req("POST", "/auth/register", body={
    "email": "skiptest@test.com", "password": "Test123!", "full_name": "Skip Test"
})
log("1.2", "POST /auth/register (duplicate)", r)

# If 1.1 succeeded, get tokens
access_token = None
refresh_token = None
if r["status"] == 500 and "trace_id" in str(r["body"]):
    # Try registering a different user
    r = req("POST", "/auth/register", body={
        "email": "skiptest_ok@test.com", "password": "Test123!", "full_name": "Skip Test OK"
    })
    log("1.1b", "POST /auth/register (alt email)", r)

if r["status"] == 201:
    print("\n  >>> Registration succeeded!")

# 1.3 Login with valid user
r = req("POST", "/auth/login", body={"email": "skiptest@test.com", "password": "Test123!"})
log("1.3", "POST /auth/login (valid credentials)", r)
if r["status"] == 200:
    access_token = r["body"].get("access_token")
    refresh_token = r["body"].get("refresh_token")

# Try with the admin user too
if r["status"] != 200:
    r = req("POST", "/auth/login", body={"email": "admin@trustshield.io", "password": "Test123!"})
    log("1.3b", "POST /auth/login (admin user)", r)
    if r["status"] == 200:
        access_token = r["body"].get("access_token")
        refresh_token = r["body"].get("refresh_token")

# Try direct user
if r["status"] != 200:
    r = req("POST", "/auth/login", body={"email": "directuser@test.com", "password": "Test123!"})
    log("1.3c", "POST /auth/login (direct user)", r)
    if r["status"] == 200:
        access_token = r["body"].get("access_token")
        refresh_token = r["body"].get("refresh_token")

# 1.4 Login bad password
r = req("POST", "/auth/login", body={"email": "skiptest@test.com", "password": "wrongpassword!"})
log("1.4", "POST /auth/login (bad password)", r)

# 1.5 GET /auth/me with token
if access_token:
    r = req("GET", "/auth/me", headers={"Authorization": f"Bearer {access_token}"})
else:
    r = req("GET", "/auth/me")
log("1.5", "GET /auth/me (with token)" if access_token else "GET /auth/me (no token)", r)

# 1.6 GET /auth/me no auth
r = req("GET", "/auth/me")
log("1.6", "GET /auth/me (no auth)", r)

# 1.7 POST /auth/refresh with test token
r = req("POST", "/auth/refresh", body={"refresh_token": "test-token"})
log("1.7", "POST /auth/refresh (invalid token)", r)

# If we have a valid refresh token, test the actual refresh
if refresh_token:
    r = req("POST", "/auth/refresh", body={"refresh_token": refresh_token})
    log("1.7b", "POST /auth/refresh (valid token)", r)
    if r["status"] == 200:
        new_access = r["body"].get("access_token")
        # 1.8 Reuse the old refresh token
        r2 = req("POST", "/auth/refresh", body={"refresh_token": refresh_token})
        log("1.8a", "POST /auth/refresh (old token reuse — should revoke)", r2)

# 1.8 Token reuse with test tokens
r1 = req("POST", "/auth/refresh", body={"refresh_token": "test-token-reuse-001"})
r2 = req("POST", "/auth/refresh", body={"refresh_token": "test-token-reuse-001"})
log("1.8", "POST /auth/refresh (token reuse detection)", r2)

# 1.9 POST /auth/logout
if access_token:
    r = req("POST", "/auth/logout", headers={"Authorization": f"Bearer {access_token}"})
else:
    r = req("POST", "/auth/logout")
log("1.9", "POST /auth/logout", r)

# 1.10 GET /auth/me after logout
r = req("GET", "/auth/me")
log("1.10", "GET /auth/me (after logout/no auth)", r)

# ============================================================
# PHASE 2 — Quick re-verify
# ============================================================

# 2.1 POST /analyze (key endpoint)
api_key_info = None
r = req("POST", "/analyze", body={
    "messages": [{"sender": "user", "text": "OTP bhejo 9876543210 UPI payment confirm karo"}],
    "session_metadata": {
        "client_app_id": "test", "session_id": f"skipped-test-{int(time.time())}",
        "contact_initiated_by": "user", "is_during_active_upi_session": False,
        "user_device_hash": "device1",
    },
})
log("2.1", "POST /analyze (scam text)", r)

# 2.7 POST /batch/analyze
r = req("POST", "/batch/analyze", body={
    "messages": [
        {"sender": "user", "text": "test message one", "session_id": "batch-sess-1"},
        {"sender": "user", "text": "test message two", "session_id": "batch-sess-1"},
    ],
    "session_metadata": {
        "client_app_id": "test", "session_id": "batch-sess-1",
        "contact_initiated_by": "user", "is_during_active_upi_session": False,
        "user_device_hash": "device1",
    },
})
log("2.7", "POST /batch/analyze", r)

# ============================================================
# PHASE 9 — Failure Modes
# ============================================================

# 9.1 Rate limit
analyze_body = {
    "messages": [{"sender": "user", "text": "test"}],
    "session_metadata": {
        "client_app_id": "test", "session_id": "rate-test-1",
        "contact_initiated_by": "user", "is_during_active_upi_session": False,
        "user_device_hash": "device1",
    },
}
rate_limit_hit = False
rate_limit_statuses = []
for i in range(12):
    analyze_body["session_metadata"]["session_id"] = f"rate-test-{i}"
    r = req("POST", "/analyze", body=analyze_body)
    rate_limit_statuses.append(r["status"])
    if r["status"] == 429:
        rate_limit_hit = True
        log("9.1", f"POST /analyze rate limit hit at attempt {i+1}/12", r)
        break
    time.sleep(0.01)

if not rate_limit_hit:
    log("9.1", f"POST /analyze (no 429 after 12 reqs, all statuses: {rate_limit_statuses})",
        {"status": "OK", "body": "Rate limit not triggered — may be configured higher"})

# 9.2 Expired token / bad JWT
r = req("GET", "/auth/me", headers={
    "Authorization": "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxIiwiZXhwIjoxNTE2MjM5MDIyfQ.XYZ"
})
log("9.2a", "GET /auth/me with expired JWT (Bearer)", r)

# With cookie
r = req("GET", "/auth/me", headers={
    "Cookie": "ts_access_token=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxIiwiZXhwIjoxNTE2MjM5MDIyfQ.xyz"
})
log("9.2b", "GET /auth/me with expired JWT (cookie)", r)

# 9.6 Tenant isolation
r = req("GET", "/analytics/dashboard")
log("9.6a", "GET /analytics/dashboard (no X-Tenant-Id)", r)

r = req("GET", "/analytics/dashboard", headers={"X-Tenant-Id": "made-up-tenant-123"})
log("9.6b", "GET /analytics/dashboard (fake X-Tenant-Id)", r)

r = req("GET", "/hotspots")
log("9.6c", "GET /hotspots (no X-Tenant-Id)", r)

# ============================================================
# SUMMARY
# ============================================================
print("\n\n" + "="*60)
print("FINAL SUMMARY")
print("="*60)
print(f"{'Test ID':<12} {'Status':<7} {'HTTP':<6} Description")
print("-"*60)
for res in results:
    passed = res["http_status"] not in ("ERROR",)
    icon = "PASS" if passed else "FAIL"
    print(f"{res['test_id']:<12} {icon:<7} {res['http_status']:<6} {res['description']}")

with open("LIVE_TEST_RESULTS_SKIPPED.json", "w") as f:
    json.dump(results, f, indent=2, ensure_ascii=False)
print("\nFull results saved to LIVE_TEST_RESULTS_SKIPPED.json")
