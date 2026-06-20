# TrustShield

**Real-time AI-powered fraud detection platform for UPI and digital payments in India.**

TrustShield analyzes chat conversations, voice calls, and images in real-time to detect and prevent financial scams. It protects 500M+ UPI users from vishing, OTP harvesting, refund scams, remote access exploitation, and social engineering attacks.

---

## Features

- **Real-time detection** — <300ms P95 latency for fraud classification
- **Multi-modal analysis** — Text, voice (WebSocket), and image/QR scanning
- **Bilingual warnings** — English + Hindi (Hinglish) intervention messages
- **Graph intelligence** — Neo4j-powered fraud ring detection and risk propagation
- **Explainability** — LLM-grounded RAG chat for "why was this flagged?" answers
- **Intervention engine** — Soft warnings, hard blocks, transaction freezes, WhatsApp alerts
- **Recovery workflow** — Step-by-step victim recovery with auto-complaint PDFs and 1930 submission
- **Compliance** — RBI quarterly reports, DPDP data register, immutable audit chains
- **Multi-tenancy** — Tenant isolation, SSO/SAML, SCIM provisioning, RBAC
- **Billing** — Stripe metered billing with usage quotas and plan tiers
- **Client SDKs** — Web (TypeScript), Android (Kotlin), iOS (Swift)

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| **Backend** | Python 3.11+, FastAPI, SQLAlchemy 2.0 async, Pydantic v2 |
| **Frontend** | Next.js 15, React 19, TypeScript, Tailwind CSS 4, shadcn/ui |
| **Database** | PostgreSQL (pgvector), Neo4j, Redis |
| **Messaging** | Apache Kafka (production), Redis Streams (dev) |
| **ML** | ONNX Runtime, MuRIL, XGBoost, keyword classifier fallback |
| **Voice** | faster-whisper (local), Deepgram Nova-3 (cloud) |
| **Auth** | JWT (httpOnly cookies), SAML SSO, OIDC, SCIM, RBAC |
| **PII** | AES-256-GCM envelope encryption, AWS KMS, tokenization |
| **Billing** | Stripe (metered, 4 tiers) |
| **Observability** | OpenTelemetry, Prometheus, Sentry, Grafana |
| **Deployment** | Docker, Kubernetes (Helm), Terraform, Argo CD |

---

## Architecture

```
                         ┌──────────────────────────────────────────────┐
   Banks / SDK / Bot ──▶ │  Edge: Cloudflare WAF + mTLS + Rate-limit    │
                         └──────────────────────┬───────────────────────┘
                                                ▼
                         ┌──────────────────────────────────────────────┐
                         │  FastAPI (async) — 32 routers, 93 endpoints  │
                         │  • analyze • scan • webhook • voice(WS)      │
                         │  • explain • intel • recovery • behavioral   │
                         └───┬───────────┬───────────┬──────────┬───────┘
                             │           │           │          │
                  ┌──────────▼──┐  ┌──────▼─────┐ ┌───▼────┐ ┌───▼────────┐
                  │ NLP Service │  │ Graph Svc  │ │ Vector │ │ Feature    │
                  │ (ONNX +     │  │ (Neo4j)    │ │(pgvec) │ │ Store      │
                  │  keywords)  │  │            │ │        │ │            │
                  └──────────┬──┘  └────────────┘ └────────┘ └────────────┘
                             │
                  ┌──────────▼──────────────────────────────────┐
                  │ Redpanda (events) ─▶ Celery Workers          │
                  │   • audit • alerts • graph-build • retrain   │
                  └──────────┬──────────────────────────────────┘
                             │
        ┌────────────────────┼────────────────────┬──────────────┐
        ▼                    ▼                    ▼              ▼
   PostgreSQL 16       ClickHouse          Redis 7         S3 / MinIO
   (asyncpg)           (analytics)         (cache)         (evidence)
```

---

## Project Structure

```
TrustShield/
├── backend/                    # FastAPI Python backend
│   ├── app/
│   │   ├── api/v1/            # 32 API routers (93 endpoints)
│   │   ├── models/            # 22 SQLAlchemy ORM models
│   │   ├── schemas/           # Pydantic v2 request/response schemas
│   │   ├── services/          # 20+ service packages
│   │   ├── middleware/         # Audit, billing, tenant context, cell routing
│   │   ├── workers/           # Celery tasks, Kafka consumer
│   │   ├── utils/             # PII masking, regex patterns
│   │   ├── auth.py            # JWT validation, RBAC dependencies
│   │   ├── config.py          # pydantic-settings (~100 env vars)
│   │   ├── database.py        # SQLAlchemy async/sync engines
│   │   └── main.py            # FastAPI app, lifespan, router registration
│   ├── ml/                    # ML training pipeline, ONNX export, drift monitoring
│   ├── alembic/               # Database migrations
│   └── tests/                 # Unit, integration, contract, load tests
├── frontend/                   # Next.js 15 frontend
│   ├── app/[locale]/           # i18n routes (EN/HI/TA/TE)
│   ├── components/             # shadcn/ui components, AppShell, Sidebar
│   ├── lib/                    # API client, auth context, utilities
│   ├── messages/               # i18n translation files
│   └── e2e/                    # Playwright E2E tests
├── sdk/                        # Client SDKs
│   ├── web/                    # TypeScript SDK (@trustshield/web-sdk)
│   ├── android/                # Kotlin SDK (TrustShieldManager)
│   └── ios/                    # Swift Package
├── infra/                      # Infrastructure
│   ├── docker-compose.yml      # 10-service dev stack
│   ├── helm/trustshield/       # Kubernetes Helm chart
│   ├── terraform/              # AWS modules (RDS, ElastiCache, KMS, S3)
│   ├── dashboards/             # Grafana dashboards
│   └── alerts/                 # Prometheus rules + Alertmanager
├── docs/                       # Architecture, API guide, threat model
└── scripts/                    # OpenAPI export, i18n lint
```

---

## Quick Start

### Prerequisites

- Docker & Docker Compose
- Python 3.11+
- Node.js 18+

### Development Stack

```bash
# Clone and start all services
git clone https://github.com/ujjawalranjan09/TrustShield.git
cd TrustShield
make dev

# Services available at:
# API:        http://localhost:8000
# Frontend:   http://localhost:3000
# Neo4j:      http://localhost:7474
# MinIO:      http://localhost:9001
# PgBouncer:  localhost:6432
```

### Manual Setup

```bash
# Backend
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Frontend
cd frontend
npm install
npm run dev

# Celery Workers
cd backend
celery -A app.workers.celery_app worker -l info
```

---

## API Overview

### Core Detection Endpoints

| Endpoint | Method | Auth | Description |
|----------|--------|------|-------------|
| `/api/v1/analyze` | POST | JWT | Full NLP pipeline: chat → risk score → intervention |
| `/api/v1/webhook/pre-transaction` | POST | API Key | Bank-side transaction pre-screening (<100ms) |
| `/api/v1/scan-message` | POST | API Key | Stateless single-message scam scan |
| `/api/v1/consumer/scan` | POST | None | Public consumer scanner (PWA/WhatsApp bot) |
| `/api/v1/voice/analyze` | POST | API Key | Voice transcript vishing analysis |
| `/api/v1/analyze-image` | POST | API Key | QR code and image fraud detection |
| `/api/v1/behavioral-signal` | POST | API Key | Android SDK behavioral biometrics |
| `/api/v1/analyze/batch` | POST | API Key | Batch analysis (up to 100 sessions) |

### Intelligence & Graph

| Endpoint | Method | Auth | Description |
|----------|--------|------|-------------|
| `/api/v1/intel/register-bank` | POST | None | Register bank partner (returns API key) |
| `/api/v1/intel/lookup` | POST | API Key | Cross-bank entity risk lookup |
| `/api/v1/graph/visualize` | GET | JWT | Cytoscape-compatible graph JSON |
| `/api/v1/graph/entity/{type}/{value}` | GET | Role | Entity neighborhood + ring membership |
| `/api/v1/graph/path` | GET | Role | Shortest path between entities |

### Example: Analyze Request

```bash
curl -X POST http://localhost:8000/api/v1/analyze \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [{"sender": "agent", "text": "Please share your AnyDesk ID 123456789"}],
    "session_metadata": {
      "client_app_id": "app_1",
      "session_id": "sess_1",
      "contact_initiated_by": "unknown",
      "is_during_active_upi_session": true,
      "user_device_hash": "hash1",
      "prior_reports_for_sender": 2
    }
  }'
```

### Example: Response

```json
{
  "session_id": "sess_1",
  "risk_score": 85,
  "risk_level": "CRITICAL",
  "recommended_action": "FREEZE_AND_REPORT",
  "flagged_entities": [
    {"entity_type": "ANYDESK", "value": "123456789", "confidence_score": 0.99}
  ],
  "warning_message_en": "Warning: High risk of fraud! We have disabled PIN entry temporarily.",
  "warning_message_hi": "Chetawani: Fraud ka khatra! PIN entry kuch samay ke liye block kar diya hai.",
  "intervention_type": "FREEZE_AND_REPORT"
}
```

Full API documentation: `http://localhost:8000/docs` (Swagger UI)

---

## Testing

```bash
# Backend unit + integration tests
cd backend
pytest tests/unit/ -v
pytest tests/integration/ -v

# Frontend unit tests
cd frontend
npm run test

# E2E tests (Playwright)
cd frontend
npm run test:e2e

# Load tests (k6)
cd backend/tests/load
k6 run k6_analyze.js
```

---

## Deployment

### Docker Compose (Development)

```bash
make dev    # Start all 10 services
make stop   # Stop all services
```

### Kubernetes (Production)

```bash
cd infra
terraform apply -var-file=envs/prod.tfvars
helm install trustshield helm/trustshield/ -f helm/trustshield/values.yaml
```

### CI/CD

GitHub Actions pipeline with 13 jobs:
- Gitleaks secret scanning
- Ruff/ESLint linting
- pytest unit + integration tests
- Alembic migration validation
- Grafana dashboard validation
- Graph lifecycle tests
- RAG grounding evaluation
- i18n lint
- Cross-tenant isolation suite
- SDK parity checks (Web/Android/iOS)

---

## Security

- **AuthN/Z**: JWT httpOnly cookies + rotating refresh tokens + SAML/OIDC SSO + RBAC/ABAC
- **PII Protection**: AES-256-GCM envelope encryption (AWS KMS), HMAC tokenization, redaction at external boundaries
- **Audit**: Hash-chain integrity verification, append-only logs
- **Compliance**: DPDP Act data register, RBI quarterly reports, 1930 cybercrime submission
- **Infrastructure**: mTLS, HMAC-signed webhooks, rate limiting, gitleaks + Trivy CI scanning

---

## Monitoring

- **Grafana Dashboards**: Overview, billing, model performance, compliance, SLO
- **Prometheus Alerts**: SLA burn, model drift, audit chain breaks, billing meter lag
- **Sentry**: Error tracking with release health
- **OpenTelemetry**: Distributed tracing across all services

---

## License

MIT License — see [LICENSE](LICENSE) for details.

---

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit changes (`git commit -m 'Add amazing feature'`)
4. Push to branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

---

## Contact

For support or questions, contact the TrustShield team.
