# TrustShield Penetration Test Scope

## Overview

This document defines the scope, boundaries, and rules of engagement for authorized penetration testing of the TrustShield platform.

**Testing Window:** [START DATE] to [END DATE]
**Authorized Tester(s):** [NAME / ORGANIZATION]
**Authorization Reference:** [AUTHORIZATION DOCUMENT ID]

---

## In-Scope Endpoints

### Public API (`https://api.trustshield.example.com`)

| Endpoint | Method | Auth Required | Notes |
|----------|--------|---------------|-------|
| `/api/v1/analyze` | POST | Yes (JWT) | Primary fraud analysis endpoint |
| `/api/v1/batch` | POST | Yes (JWT) | Batch analysis |
| `/api/v1/explain` | POST | Yes (JWT) | Explainability endpoint |
| `/api/v1/feedback` | POST | Yes (JWT) | Analyst feedback submission |
| `/api/v1/scan` | POST | Yes (API key) | Payment scanning |
| `/api/v1/reputation/{id}` | GET | Yes (JWT) | Entity reputation lookup |
| `/api/v1/graph/query` | POST | Yes (JWT) | Graph relationship queries |
| `/api/v1/audit/logs` | GET | Yes (admin JWT) | Audit log access |
| `/api/v1/auth/login` | POST | No | Authentication endpoint |
| `/api/v1/auth/refresh` | POST | No | Token refresh |
| `/api/v1/billing/usage` | GET | Yes (JWT) | Billing usage |
| `/api/v1/dpdp/consent` | POST | Yes (JWT) | DPDP consent management |

### Bank API (`https://api.trustshield.example.com`)

| Endpoint | Method | Auth Required | Notes |
|----------|--------|---------------|-------|
| `/api/v1/banker/dashboard` | GET | Yes (bank API key) | Bank dashboard data |
| `/api/v1/banker/alerts` | GET | Yes (bank API key) | Bank-specific alerts |
| `/api/v1/webhook/stripe` | POST | Yes (Stripe signature) | Payment webhooks |

### Admin API (Internal Only)

| Endpoint | Method | Auth Required | Notes |
|----------|--------|---------------|-------|
| `/api/v1/intervention/block` | POST | Yes (admin JWT) | Account blocking |
| `/api/v1/compliance/report` | GET | Yes (compliance JWT) | Regulatory reports |
| `/api/v1/intel/rules` | GET | Yes (admin JWT) | Intelligence rules |

### WebSocket

| Endpoint | Protocol | Auth Required | Notes |
|----------|----------|---------------|-------|
| `/api/v1/ws/dashboard` | WSS | Yes (JWT) | Real-time dashboard |

### Authentication Mechanisms

| Mechanism | Usage | Token Lifetime |
|-----------|-------|---------------|
| JWT (RS256) | Consumer/Bank/Admin sessions | 15 min access, 7 day refresh |
| API Key (X-API-Key) | Legacy bank integrations | Static, rotatable |
| Stripe Webhook Sig | Payment event verification | Per-request HMAC |

---

## Out-of-Scope

The following are **explicitly excluded** from testing:

### Infrastructure (AWS)
- AWS account-level security (IAM policies, root account)
- VPC/networking configuration (security groups, NACLs)
- EKS cluster node security
- RDS instance-level access
- S3 bucket policies
- CloudFront/WAF configuration

### Third-Party Services
- Stripe API and dashboard
- AWS KMS internals
- Neo4j Aura managed service
- Sentry error tracking

### Internal Tooling
- CI/CD pipelines (GitHub Actions)
- Argo CD configuration
- Helm chart internals
- Monitoring stack (Grafana, Prometheus, Loki)

### Social Engineering
- Phishing attacks on employees
- Physical security testing
- Phone-based social engineering

---

## Test Accounts

| Account Type | Email | Role | Plan | Notes |
|--------------|-------|------|------|-------|
| Consumer | test-consumer@trustshield.example.com | user | Free | 1000 API calls/day |
| Consumer | test-premium@trustshield.example.com | user | Pro | 10000 API calls/day |
| Bank | test-bank-api@trustshield.example.com | bank_admin | Enterprise | Full bank API access |
| Bank | test-bank-readonly@trustshield.example.com | bank_user | Enterprise | Read-only bank access |
| Admin | test-admin@trustshield.example.com | admin | - | Full admin access |
| Admin | test-compliance@trustshield.example.com | compliance | - | Compliance reports only |

### Test API Keys

| Key Name | Key Value | Permissions |
|----------|-----------|-------------|
| Bank API Key (read) | `ts_test_key_read_***` | Read-only bank data |
| Bank API Key (write) | `ts_test_key_write_***` | Read + write bank data |
| Legacy API Key | `ts_test_legacy_***` | Legacy endpoint access |

### Test Data

- Synthetic fraud dataset: `backend/tests/fixtures/synthetic_fraud.json`
- Test UPI IDs: `test@upi`, `fraud@upi`, `benign@upi`
- Test account numbers: `1234567890` (benign), `9876543210` (flagged)

---

## Rules of Engagement

### Permitted
- Active exploitation of in-scope endpoints
- Authentication testing (brute force within rate limits)
- Input validation testing (injection, overflow)
- Authorization testing (privilege escalation, IDOR)
- Session management testing (token handling, logout)
- API abuse testing (rate limit bypass, quota exhaustion)

### Prohibited
- Denial of service attacks against production
- Data exfiltration beyond test account data
- Modification of production data (except test accounts)
- Accessing other customers' data
- Testing during peak hours (09:00-18:00 IST)
- Using discovered vulnerabilities for purposes beyond this engagement

### Reporting

| Severity | Description | Response Time |
|----------|-------------|---------------|
| Critical | Remote code execution, auth bypass, data breach | Immediate (1 hour) |
| High | Privilege escalation, significant data exposure | 24 hours |
| Medium | Information disclosure, rate limit bypass | 72 hours |
| Low | Minor issues, best practice violations | Next sprint |

---

## Responsible Disclosure Terms

1. **Notification**: All findings must be reported to trustshield-security@example.com within 48 hours of discovery.

2. **Confidentiality**: Test results are confidential and must not be shared with third parties.

3. **Safe Harbor**: Findings will not be used for legal action against testers acting within scope.

4. **Embargo**: Public disclosure requires 90-day embargo period from remediation.

5. **Scope Creep**: Any testing beyond defined scope requires written authorization.

6. **Liability**: Testers are responsible for any damage caused outside permitted activities.

7. **Data Handling**: Any test data collected must be destroyed within 30 days of report submission.

---

## Contact

| Role | Name | Email | Phone |
|------|------|-------|-------|
| Security Lead | [NAME] | trustshield-security@example.com | [PHONE] |
| Engineering Lead | [NAME] | trustshield-eng@example.com | [PHONE] |
| Legal | [NAME] | trustshield-legal@example.com | [PHONE] |
