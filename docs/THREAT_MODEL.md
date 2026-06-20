# TrustShield Threat Model (STRIDE Analysis)

## Trust Boundaries

```
┌─────────────────────────────────────────────────────────────────┐
│                        INTERNET                                  │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐                      │
│  │ Consumer  │  │ Bank API │  │  Admin   │                      │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘                      │
│───────┼──────────────┼──────────────┼─────── TB1: Internet ──────│
│       │              │              │                            │
│  ┌────▼──────────────▼──────────────▼────┐                      │
│  │            API Gateway / ALB          │                      │
│  │     (TLS termination, rate limiting)  │                      │
│  └────────────────┬─────────────────────┘                      │
│───────────────────┼─────── TB2: Internal API ──────────────────│
│                   │                                             │
│  ┌────────────────▼─────────────────────┐  ┌────────────────┐  │
│  │         FastAPI Application          │  │  Model Service │  │
│  │  ┌──────────┐  ┌──────────────────┐  │  │  (ML inference)│  │
│  │  │ API v1   │  │ Audit Middleware  │  │  └───────┬────────┘  │
│  │  └──────────┘  └──────────────────┘  │          │           │
│  └───────┬──────────────┬───────────────┘          │           │
│──────────┼──────────────┼──────────────────────────┼───────────│
│          │              │                          │           │
│  TB3: Data Layer        │                          │           │
│  ┌──────▼───────┐  ┌───▼────────┐  ┌─────────────▼────────┐  │
│  │  PostgreSQL  │  │   Redis    │  │    KMS (AWS)         │  │
│  │  (RDS)       │  │            │  │  (PII encryption)    │  │
│  └──────────────┘  └────────────┘  └──────────────────────┘  │
│───────────────────────────────────────────────────────────────│
│  TB4: Worker Layer                                            │
│  ┌────────────────────────────────────┐                       │
│  │  Celery Workers (rollup, retention)│                       │
│  └────────────────────────────────────┘                       │
└─────────────────────────────────────────────────────────────────┘
```

## 1. Public API (Consumer → API Gateway → FastAPI)

### Threats
| STRIDE | Threat | Impact |
|--------|--------|--------|
| **S** | Spoofing: Attacker impersonates consumer with stolen JWT | Unauthorized transaction analysis |
| **T** | Tampering: Request body manipulation mid-transit | Incorrect fraud scores |
| **R** | Repudiation: Consumer denies requesting analysis | Dispute resolution failure |
| **I** | Information disclosure: API error messages leak internals | Reconnaissance for further attacks |
| **D** | Denial of service: Rate limit bypass via distributed requests | Service degradation |
| **E** | Elevation of privilege: JWT manipulation to access admin endpoints | Full system compromise |

### Controls
- JWT validation with RS256 signatures (auth.py:36-50)
- Rate limiting via slowapi (100 req/min per IP)
- CORS restricted to configured origins
- Audit middleware logs all requests with request_id
- Input validation via Pydantic schemas
- SQL injection prevented by asyncpg parameterized queries
- No stack traces in production error responses

### Residual Risk
- **Low**: JWT secret compromise (mitigated by KMS-backed key rotation)
- **Medium**: Distributed rate limit bypass (requires Redis cluster)

---

## 2. Bank API (Bank → API Gateway → FastAPI)

### Threats
| STRIDE | Threat | Impact |
|--------|--------|--------|
| **S** | Spoofing: Stolen bank API key | Access to bank-specific fraud data |
| **T** | Tampering: Modifying webhook payload | False positive/negative results |
| **R** | Repudiation: Bank denies webhook delivery | Reconciliation failures |
| **I** | Information disclosure: Bank data leaked to other tenants | Data breach, RBI violation |
| **D** | Denial of service: Bank API key abuse | Service unavailability |
| **E** | Elevation of privilege: Cross-tenant data access | Regulatory violation |

### Controls
- API key authentication per bank (X-API-Key header)
- Tenant isolation in all database queries (RLS policies)
- Webhook signature verification (Stripe-style HMAC)
- Audit trail per bank_id
- Rate limiting per bank (configurable quotas)
- Billing meter per bank (quota enforcement)

### Residual Risk
- **Low**: API key rotation gap (mitigated by mandatory rotation)
- **Medium**: Webhook replay attacks (mitigated by idempotency keys)

---

## 3. Admin Dashboard (Admin → FastAPI)

### Threats
| STRIDE | Threat | Impact |
|--------|--------|--------|
| **S** | Spoofing: Attacker gains admin session | Full system access |
| **T** | Tampering: Modifying fraud model parameters | Model degradation |
| **R** | Repudiation: Admin action not logged | Compliance failure |
| **I** | Information disclosure: PII visible in admin UI | Data breach |
| **D** | Denial of service: Admin bulk operations exhaust resources | Worker starvation |
| **E** | Elevation of privilege: Admin accesses KMS keys directly | Encryption key compromise |

### Controls
- JWT with admin role claim (enforced per-route)
- All admin actions audit-logged with actor_id
- PII fields encrypted at rest via KMS (encryption_listeners.py)
- Admin operations rate-limited (10 req/min)
- RBAC: admin, read_only, compliance roles
- Session revocation endpoint (RevokedSession model)

### Residual Risk
- **Low**: Session fixation (mitigated by httpOnly cookies, Secure flag)
- **Medium**: Insider threat (mitigated by audit trail, quarterly access review)

---

## 4. Worker (Celery → Redis/Kafka → PostgreSQL)

### Threats
| STRIDE | Threat | Impact |
|--------|--------|--------|
| **S** | Spoofing: Rogue worker connects to Redis | Task interception |
| **T** | Tampering: Modifying rollup calculations | Billing fraud |
| **R** | Repudiation: Worker task not logged | Audit gap |
| **I** | Information disclosure: Worker logs contain PII | Log-based data breach |
| **D** | Denial of service: Dead-letter queue flood | Rollup delays |
| **E** | Elevation of privilege: Worker accesses raw KMS keys | Key compromise |

### Controls
- Worker authentication via Redis AUTH + TLS
- Idempotency keys per task (idempotency.py)
- Dead-letter queue monitoring (celery_deadletter_depth alert)
- PII redaction in worker logs
- Task retry with exponential backoff
- Retention policy enforcement (retention.py)

### Residual Risk
- **Low**: Task replay (mitigated by idempotency keys)
- **Medium**: Redis compromise (mitigated by TLS, AUTH, VPC isolation)

---

## 5. Model Service (FastAPI → ML models)

### Threats
| STRIDE | Threat | Impact |
|--------|--------|--------|
| **S** | Spoofing: Rogue request to model endpoint | Model poisoning |
| **T** | Tampering: Adversarial input manipulation | Incorrect fraud scores |
| **R** | Repudiation: Model inference not logged | Audit gap |
| **I** | Information disclosure: Model architecture/weights leaked | Intellectual property theft |
| **D** | Denial of service: Resource exhaustion via large payloads | Model unavailability |
| **E** | Elevation of privilege: Model access to raw database | Data exfiltration |

### Controls
- Internal-only endpoint (no external exposure)
- Input validation and size limits (100KB max)
- Model fallback to keyword tier on failure (alerts/rules.yml)
- Drift monitoring (PSI metric, alert at > 0.2)
- No direct DB access from model service
- Inference logging without PII

### Residual Risk
- **Low**: Model poisoning via training data (mitigated by data validation pipeline)
- **Medium**: Adversarial inputs (mitigated by input sanitization, not fully solved)

---

## 6. Database (PostgreSQL on RDS)

### Threats
| STRIDE | Threat | Impact |
|--------|--------|--------|
| **S** | Spoofing: Stolen DB credentials | Full data access |
| **T** | Tampering: Direct row modification | Fraud data manipulation |
| **R** | Repudiation: DB changes not traced | Compliance failure |
| **I** | Information disclosure: DB snapshot exfiltration | Data breach |
| **D** | Denial of service: Connection pool exhaustion | API unavailability |
| **E** | Elevation of privilege: DB user gains superuser | Full system compromise |

### Controls
- SSL required for all connections (db_ssl_required=True in non-dev)
- PgBouncer connection pooling (MAX_CLIENT_CONN=100)
- RDS encryption at rest (AES-256)
- RDS automated backups with 35-day retention
- PITR enabled for point-in-time recovery
- IAM authentication (no password in prod)
- Audit triggers on sensitive tables

### Residual Risk
- **Low**: RDS snapshot exposure (mitigated by KMS encryption, IAM policies)
- **Medium**: SQL injection via application layer (mitigated by parameterized queries)

---

## 7. KMS (AWS KMS)

### Threats
| STRIDE | Threat | Impact |
|--------|--------|--------|
| **S** | Spoofing: Rogue service requests key decryption | PII exposure |
| **T** | Tampering: Key policy modification | Encryption bypass |
| **R** | Repudiation: Key usage not logged | Compliance failure |
| **I** | Information disclosure: Plaintext key in memory | Key compromise |
| **D** | Denial of service: KMS throttling | PII decryption failure |
| **E** | Elevation of privilege: Cross-account key access | Data breach |

### Controls
- KMS key policies restrict to specific IAM roles
- CloudTrail logging for all KMS operations
- Key rotation enabled (annual automatic)
- Envelope encryption for large data
- KMS endpoint via VPC (no internet exposure)
- Graceful degradation: PII_ENCRYPTION_KEY fallback for non-prod

### Residual Risk
- **Low**: Key policy misconfiguration (mitigated by SCP, quarterly audit)
- **Low**: KMS outage (mitigated by automatic failover, multi-region keys)

---

## Risk Summary

| Trust Boundary | High | Medium | Low | Total |
|----------------|------|--------|-----|-------|
| Public API | 0 | 1 | 1 | 2 |
| Bank API | 0 | 1 | 1 | 2 |
| Admin | 0 | 1 | 1 | 2 |
| Worker | 0 | 1 | 1 | 2 |
| Model Service | 0 | 1 | 1 | 2 |
| Database | 0 | 1 | 1 | 2 |
| KMS | 0 | 0 | 2 | 2 |
| **Total** | **0** | **5** | **9** | **14** |

## Review Schedule

- Full STRIDE review: Quarterly
- After major feature releases: Ad-hoc
- After security incidents: Ad-hoc
- Next scheduled review: [DATE]
