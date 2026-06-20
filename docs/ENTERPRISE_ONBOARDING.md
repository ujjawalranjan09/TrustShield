# TrustShield Enterprise Onboarding Guide

This guide walks enterprise customers through SSO, SCIM, role mapping, webhook setup, and embed console integration.

---

## 1. SSO Setup

TrustShield supports both **SAML 2.0** and **OpenID Connect (OIDC)** for single sign-on.

### SAML 2.0 Configuration

1. **Create an SSOConfig entry** for your tenant with `idp_type = "saml"`:
   - `idp_metadata_url`: Your IdP's metadata URL (e.g., `https://your-idp.com/metadata`)
   - `idp_entity_id`: The IdP entity ID (e.g., `https://accounts.google.com/o/saml2?idpid=C01234567`)
   - `idp_x509_cert`: The IdP's X.509 signing certificate (PEM format)
   - `acs_url`: Assertion Consumer Service URL — defaults to `https://api.trustshield.example.com/api/v1/auth/sso/saml/acs`
   - `sp_entity_id`: Your Service Provider entity ID

2. **Initiate login**:
   ```
   GET /api/v1/auth/sso/saml/login?tenant={tenant_slug}
   ```
   This redirects to your IdP's login page.

3. **ACS callback**: After authentication, the IdP POSTs to:
   ```
   POST /api/v1/auth/sso/saml/acs
   ```
   TrustShield validates the SAMLResponse, JIT-provisions the user, and issues a JWT.

### OIDC Configuration

1. **Create an SSOConfig entry** with `idp_type = "oidc"`:
   - `idp_metadata_url`: OIDC issuer URL (e.g., `https://login.microsoftonline.com/{tenant-id}/v2.0`)
   - `client_id`: OAuth2 client ID from your IdP
   - `client_secret_encrypted`: OAuth2 client secret (encrypted at rest)

2. **Initiate login**:
   ```
   GET /api/v1/auth/sso/oidc/login?tenant={tenant_slug}
   ```
   Redirects to the IdP's authorization endpoint with `scope=openid email groups`.

3. **Callback handling**: After consent, the IdP redirects to:
   ```
   GET /api/v1/auth/sso/oidc/callback?code={code}&state={state}
   ```
   TrustShield exchanges the code, validates the ID token, JIT-provisions the user, and issues a JWT.

### IdP-Specific Instructions

#### Okta

- **SAML**: Create an SAML 2.0 app integration. Set ACS URL to `https://api.trustshield.example.com/api/v1/auth/sso/saml/acs`.
- **OIDC**: Create an OIDC app with grant type "Authorization Code". Set redirect URI to `https://api.trustshield.example.com/api/v1/auth/sso/oidc/callback`.

#### Azure AD (Entra ID)

- **SAML**: Enterprise application → Single sign-on → SAML. Entity ID: `https://api.trustshield.example.com`. ACS URL: `https://api.trustshield.example.com/api/v1/auth/sso/saml/acs`.
- **OIDC**: App registration → Authentication → Add platform (Web). Redirect URI: `https://api.trustshield.example.com/api/v1/auth/sso/oidc/callback`.

#### Google Workspace

- **OIDC**: Google Cloud Console → APIs & Services → Credentials → Create OAuth 2.0 Client ID. Authorized redirect URI: `https://api.trustshield.example.com/api/v1/auth/sso/oidc/callback`.

---

## 2. SCIM Configuration

TrustShield implements [SCIM 2.0](https://datatracker.ietf.org/doc/html/rfc7644) for automated user provisioning and deprovisioning.

### Setup Steps

1. **Obtain a SCIM bearer token** from your tenant's SSO configuration. This token authenticates the IdP's SCIM calls.

2. **Configure your IdP** with:
   - SCIM Base URL: `https://api.trustshield.example.com/api/v1/scim/v2`
   - Bearer Token: `{your-scim-bearer-token}`

3. **Supported operations**:
   - `GET /scim/v2/Users` — List users
   - `POST /scim/v2/Users` — Create user
   - `GET /scim/v2/Users/{id}` — Get user
   - `PUT /scim/v2/Users/{id}` — Replace user
   - `PATCH /scim/v2/Users/{id}` — Partial update (activate/deactivate)
   - `GET /scim/v2/Groups` — List groups
   - `POST /scim/v2/Groups` — Create group

### IdP Configuration

#### Okta

1. Application → Provisioning → Enable SCIM
2. SCIM Base URL: `https://api.trustshield.example.com/api/v1/scim/v2`
3. OAuth2 Bearer Token: your SCIM bearer token
4. Supported features: Push Profile Updates, Push Groups

#### Azure AD (Entra ID)

1. Enterprise application → Provisioning → Automatic
2. Tenant URL: `https://api.trustshield.example.com/api/v1/scim/v2`
3. Secret Token: your SCIM bearer token
4. Mapping: Map Azure AD groups to TrustShield roles

#### Google Workspace

1. Google Cloud Console → Identity → External → SCIM
2. SCIM endpoint: `https://api.trustshield.example.com/api/v1/scim/v2`
3. Bearer token: your SCIM bearer token

---

## 3. Role Mapping

TrustShield maps IdP groups to internal roles for access control.

### Default Role Mapping

| IdP Group | TrustShield Role | Permissions |
|-----------|-----------------|-------------|
| `TrustShield Admin` | `super_admin` | Full access, tenant management, bypass isolation |
| `TrustShield Org Admin` | `org_admin` | Tenant-scoped admin, user management, billing |
| `TrustShield Analyst` | `analyst` | Scan, report, feedback, graph access |
| `TrustShield Viewer` | `viewer` | Read-only dashboard access |
| `TrustShield Bank` | `bank` | Bank dashboard, intervention management |

### Custom Role Mapping

IdP groups are passed as claims during SSO login. JIT provisioning maps them to TrustShield roles using the following logic:

1. If the IdP group matches a known role group name exactly, use that role.
2. If multiple groups are present, the highest-privilege role wins.
3. Unknown groups default to `viewer`.

### Configuring Custom Roles via SCIM

```
POST /api/v1/scim/v2/Groups
{
  "displayName": "compliance_officer",
  "members": [
    {"value": "user1@example.com"}
  ]
}
```

Built-in SCIM groups: `org_admin`, `analyst`, `viewer`, `compliance_officer`.

---

## 4. Webhook Subscription Setup

TrustShield sends signed webhook events when key actions occur (scan completed, fraud detected, etc.).

### Create a Subscription

```
POST /api/v1/webhooks/subscribe
{
  "url": "https://your-server.com/trustshield-webhook",
  "event_types": ["scan.completed", "fraud.detected", "recovery.initiated"]
}
```

**Response** includes the `secret` for signature verification — store it securely.

### Available Event Types

| Event | Description |
|-------|-------------|
| `scan.completed` | Analysis finished with risk verdict |
| `fraud.detected` | High/critical risk score detected |
| `recovery.initiated` | Victim recovery case created |
| `entity.confirmed` | Entity confirmed as fraudulent |
| `ring.detected` | Fraud ring detected |
| `intervention.triggered` | Coached intervention sent |

### Verify Webhook Signatures

Every outbound webhook includes:

```
X-TrustShield-Signature: sha256=<hmac-hex-digest>
```

**Python verification:**

```python
import hmac, hashlib

def verify_webhook_signature(payload: bytes, signature: str, secret: str) -> bool:
    expected = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(f"sha256={expected}", signature)
```

**Node.js verification:**

```javascript
import crypto from "node:crypto";

function verifyWebhookSignature(payload, signature, secret) {
  const expected = "sha256=" + crypto.createHmac("sha256", secret).update(payload).digest("hex");
  return crypto.timingSafeEqual(Buffer.from(expected), Buffer.from(signature));
}
```

### Retry Policy

- Failed dispatches are retried with exponential backoff: 1min, 5min, 15min, 60min
- Maximum 4 retries per event
- Monitor `webhook_retry_total` and `webhook_dispatch_total{result}` metrics

### Manage Subscriptions

```
GET  /api/v1/webhooks/subscriptions   # List all subscriptions
DELETE /api/v1/webhooks/{sub_id}       # Remove a subscription
```

---

## 5. Embed Console Integration

TrustShield provides an embeddable Trust Console widget for bank partner websites.

### Get an Embed Token

```
POST /api/v1/embed/token
Headers: X-API-Key: {your-bank-api-key}
{
  "tenant_id": "your-tenant-id"
}
```

**Response:**

```json
{
  "token": "eyJhbGciOiJIUzI1NiJ9...",
  "expires_in": 3600,
  "scope": "embed",
  "permissions": ["SCAN_READ", "REPORT_CREATE", "INTEL_READ"]
}
```

### Embed in HTML

```html
<iframe
  src="https://app.trustshield.example.com/embed?token={embed_token}"
  width="100%"
  height="600"
  frameborder="0"
  title="TrustShield Console"
></iframe>
```

### Embed Token Scope

Embed tokens are scoped to:
- A single tenant (cannot access other tenants)
- Limited permissions: `SCAN_READ`, `REPORT_CREATE`, `INTEL_READ`
- 1-hour expiry (configurable)
- Admin endpoints (`/tenant`, `/auth`, `/billing`, `/scim`) are blocked

### Verify Embed Token in Backend

Embed tokens are regular JWTs with `scope=embed`. The backend validates:
1. JWT signature and expiry
2. `scope` claim is `"embed"`
3. `tenant_id` claim matches the requesting tenant
4. No admin endpoints are accessible

---

## Tenant Headers and Data Scoping

All API requests are scoped to the authenticated tenant. The tenant context is resolved from:

1. **JWT token**: `tenant_id` is derived from the authenticated user's `User.tenant_id`
2. **API key**: `tenant_id` is derived from the bank's `Bank.tenant_id`
3. **Embed token**: `tenant_id` is embedded in the JWT

### Cross-Tenant Isolation

TrustShield enforces strict data isolation:
- The `TenantContextMiddleware` injects `tenant_id` into every request context
- The `query_filter` applies `tenant_id` WHERE clauses to all ORM queries
- `bypass_tenant()` is restricted to `super_admin` only and is logged for audit

### Headers

| Header | Purpose |
|--------|---------|
| `X-API-Key` | Bank API authentication |
| `Authorization: Bearer {jwt}` | Analyst JWT authentication |
| `X-Request-ID` | Client-generated request tracing |
| `X-TrustShield-Signature` | Webhook HMAC signature |

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| SSO login fails | Verify IdP metadata URL and X.509 cert are correct |
| SCIM provisioning returns 401 | Check bearer token matches the SSOConfig record |
| Webhook not received | Verify URL is reachable and returns 2xx; check retry logs |
| Embed token rejected | Ensure X-API-Key header is valid and tenant is active |
| Role mismatch after SSO | Verify IdP group names match expected role mapping |
