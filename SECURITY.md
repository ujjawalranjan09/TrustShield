# Security Policy

## Reporting a Vulnerability

If you discover a security vulnerability in TrustShield, please report it responsibly.

**Do NOT open a public GitHub issue.**

### Contact

- **Email:** security@trustshield.io
- **PGP Key:** Available at `/.well-known/security.txt`

### What to Include

- Description of the vulnerability
- Steps to reproduce
- Potential impact
- Suggested fix (if any)

### Response Timeline

- **Acknowledgment:** Within 48 hours
- **Initial assessment:** Within 1 week
- **Fix timeline:** Depends on severity
  - Critical: 24-48 hours
  - High: 1 week
  - Medium: 2 weeks
  - Low: Next release

## Security Measures

### Authentication

- JWT access tokens (15-minute expiry) stored in httpOnly cookies
- Refresh tokens with rotation and reuse detection
- Token versioning for instant session revocation
- Rate limiting on auth endpoints (10/minute)

### Authorization

- Role-Based Access Control (RBAC) with 5 roles:
  - `super_admin` — Full system access
  - `org_admin` — Tenant admin
  - `analyst` — Fraud analyst
  - `bank` — Bank partner
  - `viewer` — Read-only
- Permission-based access control for fine-grained authorization
- Tenant isolation via SQLAlchemy query filters

### Data Protection

- **PII Encryption:** AES-256-GCM envelope encryption via AWS KMS
- **Tokenization:** HMAC-SHA256 for deterministic tokenization of phone/UPI
- **Redaction:** All PII redacted before external API calls (LLM, Whisper)
- **Field-level encryption:** Sensitive columns encrypted at rest

### Audit

- Hash-chain integrity verification (tamper-evident)
- Append-only audit logs
- All state-changing operations logged

### Infrastructure

- TLS required for all database connections in production
- Redis TLS in production
- mTLS for bank-to-TrustShield traffic
- HMAC-signed webhooks

## Scope

### In Scope

- TrustShield API endpoints
- Authentication and authorization
- Data encryption and PII handling
- Infrastructure configuration
- SDK security

### Out of Scope

- Third-party services (Stripe, OpenRouter, Deepgram)
- Physical security
- Social engineering attacks

## Safe Harbor

We commit to:

- Not pursuing legal action for security research conducted in good faith
- Acknowledging your contribution
- Providing a timeline for fixes
- Credit in release notes (unless you prefer anonymity)

## Compliance

TrustShield maintains compliance with:

- RBI Cyber Security Framework
- DPDP Act 2023 (India)
- SOC 2 Type II (in progress)

For compliance-related security questions, contact compliance@trustshield.io.
