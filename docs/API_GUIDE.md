# TrustShield API Guide

Base URL: `https://api.trustshield.example.com`

All responses use a consistent JSON envelope. Errors follow:

```json
{
  "error": "ErrorClassName",
  "detail": "Human-readable message",
  "code": "MACHINE_READABLE_CODE",
  "trace_id": "abc-123"
}
```

---

## Authentication

### Bank API Key (X-API-Key)

Bots and bank-side integrations authenticate via the `X-API-Key` header. The key is set in the `API_KEY` environment variable on the server.

```
X-API-Key: ts_live_abc123
```

Endpoints protected by `verify_api_key`: `/api/v1/analyze`, `/api/v1/webhook/pre-transaction`.

### Analyst JWT (Bearer Token)

Analysts (UI users) authenticate with a JWT issued by `/api/v1/auth/login`. Pass the token in the `Authorization` header or as an httpOnly cookie named `ts_access_token`.

```
Authorization: Bearer eyJhbGciOiJIUzI1NiJ9...
```

Token lifetimes: access = 15 min, refresh = 7 days. Revoked tokens are rejected.

### Role-Based Access

Use `require_role("admin", "analyst")` as a FastAPI dependency to restrict endpoints to specific roles.

---

## Pre-Transaction Webhook

**`POST /api/v1/webhook/pre-transaction`**

Banks call this endpoint to screen a UPI transaction before processing.

### Request

```json
{
  "payer_vpa": "user@bank",
  "payee_vpa": "merchant@bank",
  "amount": 5000.00,
  "device_fingerprint": "optional-device-hash",
  "geo_location": { "lat": 28.6139, "lng": 77.2090 },
  "timestamp": "2025-01-15T10:30:00Z"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `payer_vpa` | string | yes | Payer's VPA |
| `payee_vpa` | string | yes | Payee's VPA |
| `amount` | float | yes | Transaction amount (> 0) |
| `device_fingerprint` | string | no | Device fingerprint hash |
| `geo_location` | object | no | `{"lat": float, "lng": float}` |
| `timestamp` | string | no | ISO-8601 timestamp |

### Response

```json
{
  "decision": "PASS",
  "reason": "No risk factors detected",
  "risk_score": 0,
  "risk_level": "low"
}
```

| Field | Description |
|-------|-------------|
| `decision` | `PASS` / `REVIEW` / `BLOCK` |
| `reason` | Semicolon-separated risk reasons |
| `risk_score` | 0–100 composite score |
| `risk_level` | `low` / `medium` / `high` / `critical` |

### Decision Logic

| Condition | Score Addition |
|-----------|---------------|
| Amount > ₹50,000 | +30 |
| Payer VPA == Payee VPA | +50 |
| Device fingerprint present | +10 |
| Geo-location provided | +5 |

| Score Range | Decision | Risk Level |
|-------------|----------|------------|
| ≥ 70 | BLOCK | critical |
| 40–69 | REVIEW | high |
| 20–39 | REVIEW | medium |
| < 20 | PASS | low |

---

## Chat Analysis

**`POST /api/v1/analyze`**

Real-time chat session analysis. Runs the full NLP pipeline: preprocessing → entity extraction → classification → risk scoring → graph enrichment → intervention decision. Target latency: < 300ms.

### Request

```json
{
  "messages": [
    { "sender": "unknown", "text": "Send your OTP to verify your account" }
  ],
  "session_metadata": {
    "client_app_id": "banking-app-v2",
    "session_id": "sess-12345",
    "contact_initiated_by": "unknown",
    "is_during_active_upi_session": false,
    "user_device_hash": "sha256-hash",
    "prior_reports_for_sender": 0,
    "session_started_at": "2025-01-15T10:30:00Z"
  }
}
```

### Response

```json
{
  "session_id": "sess-12345",
  "risk_score": 82,
  "risk_level": "CRITICAL",
  "recommended_action": "BLOCK",
  "flagged_entities": [
    { "entity_type": "phone", "value": "9876543210", "context": "..." }
  ],
  "warning_message_en": "This message contains scam indicators...",
  "warning_message_hi": "इस संदेश में धोखाधड़ी के संकेत हैं...",
  "intervention_type": "BLOCK"
}
```

---

## Error Reference

### 401 Unauthorized

```json
{
  "error": "UnauthorizedError",
  "detail": "Missing authentication token",
  "code": "UNAUTHORIZED",
  "trace_id": "abc-123"
}
```

Causes: missing `X-API-Key` header, expired/invalid JWT, missing Bearer token.

### 403 Forbidden

```json
{
  "error": "ForbiddenError",
  "detail": "Invalid API key",
  "code": "FORBIDDEN"
}
```

Causes: invalid API key, insufficient role permissions, deactivated account.

### 422 Validation Error

```json
{
  "error": "ValidationError",
  "detail": "Field required",
  "code": "VALIDATION_ERROR"
}
```

Returned when request body fails Pydantic schema validation.

### 429 Rate Limited

```json
{
  "error": "RateLimitExceeded",
  "detail": "Rate limit exceeded: 100 per minute",
  "code": "RATE_LIMITED"
}
```

Includes a `Retry-After` header with seconds until the window resets.

### 5xx Server Error

```json
{
  "error": "InternalServerError",
  "detail": "An unexpected error occurred. Please try again later.",
  "code": "INTERNAL_ERROR",
  "trace_id": "abc-123"
}
```

Always include `trace_id` for support debugging.

---

## Rate Limits

Limits are enforced per API key or per IP (for unauthenticated requests).

| Plan | Analyze | Webhook | Scan | Auth |
|------|---------|---------|------|------|
| Free | 60/min | 100/min | 30/min | 10/min |
| Pro | 300/min | 1000/min | 120/min | 10/min |
| Bank | 1000/min | 5000/min | 500/min | 10/min |
| Enterprise | 5000/min | 20000/min | 2000/min | 10/min |

When rate limited, the response includes a `Retry-After` header.

---

## Webhook Signature Verification

When banks integrate TrustShield as an outbound webhook (TrustShield → Bank), each payload is signed with HMAC-SHA256. Verify the signature:

```
X-TrustShield-Signature: sha256=<hex-digest>
```

Python:

```python
import hmac, hashlib

def verify_signature(payload: bytes, signature: str, secret: str) -> bool:
    expected = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(f"sha256={expected}", signature)
```

Node.js:

```js
import crypto from "node:crypto";

function verifySignature(payload, signature, secret) {
  const expected = "sha256=" + crypto.createHmac("sha256", secret).update(payload).digest("hex");
  return crypto.timingSafeEqual(Buffer.from(expected), Buffer.from(signature));
}
```

---

## Unified Verdict Schema

All three analysis modalities (text, voice, image) return a consistent `Verdict` object:

```json
{
  "session_id": "sess-12345",
  "is_scam": true,
  "scam_type": "vishing",
  "risk_score": 72.5,
  "risk_level": "HIGH",
  "confidence": 0.88,
  "recommended_action": "HARD_BLOCK",
  "entities": [
    {
      "entity_type": "phone",
      "value": "9876543210",
      "start_char": 0,
      "end_char": 10,
      "confidence_score": 0.95
    }
  ],
  "modality": "TEXT",
  "attributions": [
    {
      "feature": "urgency_words",
      "value": 1.0,
      "shap_value": 0.4,
      "direction": "increases"
    }
  ],
  "model_tier": "standard",
  "created_at": "2025-01-15T10:30:00Z"
}
```

| Field | Type | Description |
|-------|------|-------------|
| `session_id` | string | Unique session identifier |
| `is_scam` | boolean | Whether the input is classified as scam |
| `scam_type` | enum | `vishing`, `phishing`, `fake_support`, `otp_harvesting`, `remote_access`, `refund_scam`, `sim_swap`, `unknown` |
| `risk_score` | float (0–100) | Composite risk score |
| `risk_level` | enum | `LOW`, `MEDIUM`, `HIGH`, `CRITICAL` |
| `confidence` | float (0–1) | Model confidence |
| `recommended_action` | enum | `NONE`, `SOFT_WARNING`, `HARD_BLOCK`, `FREEZE_AND_REPORT`, `CRITICAL_REPORT`, `COACHED_VICTIM_INTERVENTION` |
| `entities` | array | Extracted entities with type, value, position, confidence |
| `modality` | enum | `TEXT`, `VOICE`, `IMAGE` |
| `attributions` | array | SHAP-based feature attributions |
| `model_tier` | string | `standard`, `ultra`, or `unknown` |
| `created_at` | datetime | ISO-8601 timestamp |

---

## Tenant Headers and Data Scoping

All API requests are scoped to the authenticated tenant. The tenant context is resolved automatically:

1. **JWT token**: `tenant_id` derived from the authenticated user's `User.tenant_id`
2. **API key**: `tenant_id` derived from the bank's `Bank.tenant_id`
3. **Embed token**: `tenant_id` embedded in the JWT

### Cross-Tenant Isolation

TrustShield enforces strict multi-tenant data isolation:

- `TenantContextMiddleware` injects `tenant_id` into every request context
- A query filter applies `tenant_id` WHERE clauses to all ORM queries transparently
- `bypass_tenant()` is restricted to `super_admin` only and is audit-logged
- Every authenticated read endpoint returns **zero rows** from other tenants

### Headers

| Header | Purpose |
|--------|---------|
| `X-API-Key` | Bank API authentication |
| `Authorization: Bearer {jwt}` | Analyst JWT authentication |
| `X-Request-ID` | Client-generated request tracing |

---

## Webhook Signature Verification

When TrustShield sends outbound webhooks (TrustShield → Bank), each payload is signed with HMAC-SHA256. Verify the signature via the `X-TrustShield-Signature` header:

```
X-TrustShield-Signature: sha256=<hex-digest>
```

The signature is computed as `HMAC-SHA256(webhook_secret, raw_request_body)`.

Python:

```python
import hmac, hashlib

def verify_signature(payload: bytes, signature: str, secret: str) -> bool:
    expected = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(f"sha256={expected}", signature)
```

Node.js:

```js
import crypto from "node:crypto";

function verifySignature(payload, signature, secret) {
  const expected = "sha256=" + crypto.createHmac("sha256", secret).update(payload).digest("hex");
  return crypto.timingSafeEqual(Buffer.from(expected), Buffer.from(signature));
}
```

**Available event types:** `scan.completed`, `fraud.detected`, `recovery.initiated`, `entity.confirmed`, `ring.detected`, `intervention.triggered`

**Retry policy:** Exponential backoff (1min → 5min → 15min → 60min), max 4 retries.

---

## Embed Token Flow

Embed a read-only Trust Console widget in bank partner websites.

### Step 1: Issue an Embed Token

```
POST /api/v1/embed/token
Headers: X-API-Key: {bank-api-key}
{
  "tenant_id": "your-tenant-id"
}
```

Response:

```json
{
  "token": "eyJhbGciOiJIUzI1NiJ9...",
  "expires_in": 3600,
  "scope": "embed",
  "permissions": ["SCAN_READ", "REPORT_CREATE", "INTEL_READ"]
}
```

### Step 2: Embed in HTML

```html
<iframe
  src="https://app.trustshield.example.com/embed?token={embed_token}"
  width="100%" height="600" frameborder="0"
  title="TrustShield Console"
></iframe>
```

### Embed Scope

- Scoped to a single tenant; cannot access other tenants
- Limited permissions: `SCAN_READ`, `REPORT_CREATE`, `INTEL_READ`
- Admin endpoints (`/tenant`, `/auth`, `/billing`, `/scim`) are blocked
- 1-hour token expiry

---

## SCIM Endpoints Reference

SCIM 2.0 endpoints for automated user provisioning. Authenticated via Bearer token from your SSOConfig.

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/v1/scim/v2/Users` | List users for the tenant |
| `POST` | `/api/v1/scim/v2/Users` | Create a new user |
| `GET` | `/api/v1/scim/v2/Users/{id}` | Get a single user |
| `PUT` | `/api/v1/scim/v2/Users/{id}` | Replace a user |
| `PATCH` | `/api/v1/scim/v2/Users/{id}` | Partial update (activate/deactivate) |
| `GET` | `/api/v1/scim/v2/Groups` | List role groups |
| `POST` | `/api/v1/scim/v2/Groups` | Create a custom role group |

**Authentication:** All SCIM requests require:

```
Authorization: Bearer {scim-bearer-token}
```

**Role mapping:** IdP groups are mapped to TrustShield roles (`super_admin`, `org_admin`, `analyst`, `viewer`). Unknown groups default to `viewer`.

**Deactivation:** PATCH `{"Operations": [{"path": "active", "value": false}]}` revokes all active sessions and increments `token_version`.

---

## Graph Endpoints

### Entity Neighborhood

**`GET /api/v1/graph/visualize?entity={value}&depth={1-3}&mask_entities={bool}`**

Returns Cytoscape-compatible graph JSON for an entity and its neighbors.

```json
{
  "nodes": [
    { "data": { "id": "abc123", "label": "9876543...", "risk": 0.85, "entity_type": "phone" } }
  ],
  "edges": [
    { "data": { "source": "abc123", "target": "def456", "label": "APPEARED_WITH" } }
  ]
}
```

### Entity Path

**`GET /api/v1/graph/path?from={entity_a}&to={entity_b}&max_hops={1-5}`**

Find the shortest path between two entities in the graph. Returns the path as a list of nodes and edges.

### Fraud Rings

**`GET /api/v1/graph/rings?risk_level={level}&status={status}&limit={50}`**

List detected fraud rings with optional filters.

```json
[
  {
    "ring_id": "ring-abc123",
    "entity_count": 12,
    "total_reports": 45,
    "top_scam_type": "phone",
    "risk_level": "critical",
    "status": "new",
    "detected_at": "2025-01-15T10:30:00Z"
  }
]
```

**`GET /api/v1/graph/rings/{ring_id}`**

Detailed ring info including member entities.

---

## Reputation Badge Embed Widget

Embed a live reputation badge for any VPA on your website:

```html
<img src="https://api.trustshield.example.com/api/v1/reputation/user@bank/widget"
     alt="Reputation Badge" />
```

Returns an SVG badge color-coded by reputation tier:
- Green (score ≥ 80): confirmed clean
- Orange (score 50–79): suspicious
- Red (score < 50): known scammer
- Gray: unknown

Badge is cached for 1 hour (`Cache-Control: public, max-age=3600`).

---

## Quickstart: curl

```bash
# Pre-transaction webhook
curl -X POST https://api.trustshield.example.com/api/v1/webhook/pre-transaction \
  -H "Content-Type: application/json" \
  -H "X-API-Key: ts_live_abc123" \
  -d '{
    "payer_vpa": "user@bank",
    "payee_vpa": "merchant@bank",
    "amount": 5000
  }'

# Chat analysis
curl -X POST https://api.trustshield.example.com/api/v1/analyze \
  -H "Content-Type: application/json" \
  -H "X-API-Key: ts_live_abc123" \
  -d '{
    "messages": [{"sender": "unknown", "text": "Send OTP to verify"}],
    "session_metadata": {
      "client_app_id": "my-app",
      "session_id": "sess-1",
      "contact_initiated_by": "unknown",
      "is_during_active_upi_session": false,
      "user_device_hash": "abc123"
    }
  }'
```

---

## Quickstart: Python (httpx)

```python
import httpx

API_BASE = "https://api.trustshield.example.com"
API_KEY = "ts_live_abc123"

client = httpx.Client(base_url=API_BASE, headers={"X-API-Key": API_KEY})

# Pre-transaction webhook
resp = client.post("/api/v1/webhook/pre-transaction", json={
    "payer_vpa": "user@bank",
    "payee_vpa": "merchant@bank",
    "amount": 5000,
})
print(resp.json())
# {"decision": "PASS", "reason": "No risk factors detected", "risk_score": 0, "risk_level": "low"}

# Chat analysis
resp = client.post("/api/v1/analyze", json={
    "messages": [{"sender": "unknown", "text": "Send OTP to verify"}],
    "session_metadata": {
        "client_app_id": "my-app",
        "session_id": "sess-1",
        "contact_initiated_by": "unknown",
        "is_during_active_upi_session": False,
        "user_device_hash": "abc123",
    },
})
print(resp.json())
```

---

## Quickstart: Node.js (fetch)

```js
const API_BASE = "https://api.trustshield.example.com";
const API_KEY = "ts_live_abc123";

async function preTransactionCheck(payerVpa, payeeVpa, amount) {
  const resp = await fetch(`${API_BASE}/api/v1/webhook/pre-transaction`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-API-Key": API_KEY,
    },
    body: JSON.stringify({
      payer_vpa: payerVpa,
      payee_vpa: payeeVpa,
      amount,
    }),
  });
  return resp.json();
}

async function analyzeChat(text) {
  const resp = await fetch(`${API_BASE}/api/v1/analyze`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-API-Key": API_KEY,
    },
    body: JSON.stringify({
      messages: [{ sender: "unknown", text }],
      session_metadata: {
        client_app_id: "my-app",
        session_id: "sess-1",
        contact_initiated_by: "unknown",
        is_during_active_upi_session: false,
        user_device_hash: "abc123",
      },
    }),
  });
  return resp.json();
}

// Usage
const result = await preTransactionCheck("user@bank", "merchant@bank", 5000);
console.log(result);
```
