# TrustShield Production Deployment Guide

## Architecture

- **Compute**: EKS (Mumbai region `ap-south-1`) for RBI data residency
- **GitOps**: Argo CD with progressive delivery (10% → 50% → 100%)
- **Message bus**: Redpanda (Kafka-compatible, no JVM)
- **Observability**: OTel → Grafana Tempo/Loki/Prometheus + Sentry

## Production Environment Variables

All variables are loaded via `backend/app/config.py` (pydantic-settings). Secrets
are hydrated from AWS Secrets Manager at startup when `SECRETS_MANAGER_PREFIX` is set.

### Application

| Variable | Description | Dev Default | Prod Required |
|---|---|---|---|
| `APP_NAME` | Application name | `TrustShield` | No |
| `APP_VERSION` | Semantic version | `1.0.0` | No |
| `ENVIRONMENT` | Runtime environment | `development` | `production` |
| `DEBUG` | Debug mode | `false` | No |

### API / Auth

| Variable | Description | Dev Default | Prod Required |
|---|---|---|---|
| `API_KEY` | Legacy API key for bank endpoints | `""` | No |
| `ALLOWED_ORIGINS` | CORS origins (comma-separated) | `http://localhost:3000` | Yes |
| `JWT_SECRET` | HMAC signing key (min 32 chars) | `""` | Yes |
| `JWT_ALGORITHM` | JWT algorithm | `HS256` | No |
| `JWT_ACCESS_EXPIRE_MINUTES` | Access token TTL | `15` | No |
| `JWT_REFRESH_EXPIRE_DAYS` | Refresh token TTL | `7` | No |

### Database

| Variable | Description | Dev Default | Prod Required |
|---|---|---|---|
| `DATABASE_URL` | PostgreSQL async URL (must use `postgresql+asyncpg://`, `sslmode=require`) | `postgresql://user:***@localhost:5432/trustshield` | Yes |
| `DB_POOL_SIZE` | Base pool size per worker | `10` | Yes |
| `DB_MAX_OVERFLOW` | Burst headroom connections | `20` | Yes |
| `DB_POOL_TIMEOUT` | Seconds before pool-exhausted error | `30` | No |
| `DB_POOL_RECYCLE` | Connection recycle interval (sec) | `1800` | No |
| `DB_SSL_REQUIRED` | Require SSL for DB connections | `true` | Yes (must be `true`) |

### Redis

| Variable | Description | Dev Default | Prod Required |
|---|---|---|---|
| `REDIS_URL` | Redis URL (must use `rediss://` in prod) | `redis://localhost:6379/0` | Yes |

### Neo4j

| Variable | Description | Dev Default | Prod Required |
|---|---|---|---|
| `NEO4J_URI` | Bolt URI | `bolt://localhost:7687` | Yes |
| `NEO4J_USER` | Neo4j username | `neo4j` | Yes |
| `NEO4J_PASSWORD` | Neo4j password | `password` | Yes |

### Kafka / Redpanda

| Variable | Description | Dev Default | Prod Required |
|---|---|---|---|
| `KAFKA_BOOTSTRAP_SERVERS` | Bootstrap servers | `localhost:9092` | Yes |
| `EVENT_BACKEND` | Event backend (`redis` or `kafka`) | `redis` | `kafka` |

### ML / Model Service

| Variable | Description | Dev Default | Prod Required |
|---|---|---|---|
| `MURIL_MODEL_PATH` | Local ONNX model path | `trustshield/backend/ml/artifacts/muril_scam_classifier/model.onnx` | No |
| `ML_ARTIFACTS_DIR` | S3-backed artifact directory | `ml/artifacts` | Yes |
| `MODEL_VERSION` | Trained model version tag | `""` | Yes |
| `MODEL_SERVICE_URL` | Remote inference endpoint (empty = in-process) | `""` | Recommended |
| `MODEL_SERVICE_TIMEOUT_MS` | Inference request timeout | `100` | No |

### Voice / LLM

| Variable | Description | Dev Default | Prod Required |
|---|---|---|---|
| `VOICE_PROVIDER` | Voice transcription provider | `mock` | No |
| `DEEPGRAM_API_KEY` | Deepgram API key | `""` | If provider=deepgram |
| `WHISPER_MODEL_SIZE` | Whisper model size | `base` | No |
| `VOICE_SAMPLE_RATE` | Audio sample rate | `16000` | No |
| `LLM_API_KEY` | LLM provider API key | `""` | If LLM used |
| `LLM_PROVIDER` | LLM provider (`openrouter` or `local`) | `openrouter` | No |

### AWS KMS / PII Encryption

| Variable | Description | Dev Default | Prod Required |
|---|---|---|---|
| `KMS_KEY_ID` | AWS KMS key ARN for envelope encryption | `""` | Yes (or `PII_ENCRYPTION_KEY`) |
| `KMS_REGION` | KMS region | `ap-south-1` | No |
| `AWS_ACCESS_KEY_ID` | AWS access key | `""` | If not using IRSA |
| `AWS_SECRET_ACCESS_KEY` | AWS secret key | `""` | If not using IRSA |
| `PII_ENCRYPTION_KEY` | Base64-encoded 256-bit key (KMS fallback) | `""` | Yes (or `KMS_KEY_ID`) |

### AWS Secrets Manager

| Variable | Description | Dev Default | Prod Required |
|---|---|---|---|
| `SECRETS_MANAGER_PREFIX` | Secret key prefix | `""` | Yes |
| `SECRETS_MANAGER_REGION` | Secrets Manager region | `ap-south-1` | No |

### Billing (Stripe)

| Variable | Description | Dev Default | Prod Required |
|---|---|---|---|
| `BILLING_ENABLED` | Enable Stripe billing | `false` | Yes |
| `STRIPE_SECRET_KEY` | Stripe API key | `""` | If billing enabled |
| `STRIPE_WEBHOOK_SECRET` | Stripe webhook signing secret | `""` | If billing enabled |
| `STRIPE_PRICE_ID_FREE` | Stripe price ID (free tier) | `""` | If billing enabled |
| `STRIPE_PRICE_ID_PRO` | Stripe price ID (pro tier) | `""` | If billing enabled |
| `STRIPE_PRICE_ID_BANK` | Stripe price ID (bank tier) | `""` | If billing enabled |
| `STRIPE_PRICE_ID_ENTERPRISE` | Stripe price ID (enterprise tier) | `""` | If billing enabled |

### Observability

| Variable | Description | Dev Default | Prod Required |
|---|---|---|---|
| `SENTRY_DSN` | Sentry error tracking DSN | `""` | Recommended |
| `OTEL_ENDPOINT` | OpenTelemetry collector endpoint | `http://localhost:4318` | Yes |
| `LOG_LEVEL` | Python log level | `INFO` | No |

### DPDP / Compliance

| Variable | Description | Dev Default | Prod Required |
|---|---|---|---|
| `DPDP_ENABLED` | Enable DPDP compliance features | `true` | No |
| `RETENTION_SCAN_EVENTS_DAYS` | Scan event retention (days) | `730` | No |
| `RETENTION_RECOVERY_YEARS` | Recovery data retention (years) | `7` | No |

### WhatsApp

| Variable | Description | Dev Default | Prod Required |
|---|---|---|---|
| `WHATSAPP_VERIFY_TOKEN` | WhatsApp webhook verify token | `""` | If WhatsApp enabled |
| `WHATSAPP_ACCESS_TOKEN` | WhatsApp Cloud API token | `""` | If WhatsApp enabled |
| `WHATSAPP_PHONE_NUMBER_ID` | WhatsApp phone number ID | `""` | If WhatsApp enabled |

### Cybercrime / 1930

| Variable | Description | Dev Default | Prod Required |
|---|---|---|---|
| `CYBERCRIME_API_URL` | Cybercrime API endpoint | `sandbox` | No |
| `CYBERCRIME_API_KEY` | Cybercrime API key | `""` | If filing enabled |

### Celery

| Variable | Description | Dev Default | Prod Required |
|---|---|---|---|
| `CELERY_TASK_EAGER` | Run tasks synchronously (dev only) | `false` | Must be `false` |
| `CELERY_DEADLETTER_QUEUE` | Dead-letter queue name | `trustshield-deadletter` | No |

### Export

| Variable | Description | Dev Default | Prod Required |
|---|---|---|---|
| `EXPORT_SIGNING_KEY` | HMAC key for signed exports | `""` | If exports enabled |

### Rate Limits

| Variable | Description | Dev Default | Prod Required |
|---|---|---|---|
| `RATE_LIMIT_ANALYZE` | Analyze endpoint rate limit | `100/minute` | Yes |
| `RATE_LIMIT_WEBHOOK` | Webhook endpoint rate limit | `1000/minute` | Yes |
| `RATE_LIMIT_SCAN` | Scan endpoint rate limit | `60/minute` | Yes |
| `RATE_LIMIT_AUTH` | Auth endpoint rate limit | `10/minute` | Yes |

---

## HPA Configuration

Defined in `infra/helm/trustshield/values.yaml`:

```yaml
autoscaling:
  enabled: true
  minReplicas: 2
  maxReplicas: 10
  targetCPUUtilizationPercentage: 70
```

Extended config (see `infra/PERFORMANCE.md`):

```yaml
metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 70
  - type: Pods
    pods:
      metric:
        name: http_requests_per_second
      target:
        type: AverageValue
        averageValue: "400"
```

- **minReplicas: 2** — ensures at least 2 pods survive a single-node failure
  and keeps the health-check endpoint responsive during rolling deploys.
- **maxReplicas: 10** — caps cost while handling ~10× baseline traffic.
- **CPU target: 70%** — triggers scale-up before request latency degrades
  (the API serves 95th-percentile < 300ms under normal load).
- **RPS target: 400/replica** — triggers scale-up on traffic spikes even if CPU
  hasn't hit 70% (e.g., lightweight endpoints).
- **Scale-down stabilization: 300s** — prevents flapping during transient dips.

## Pool Sizing Rationale

### Application Pool (`app.config.Settings`)

| Setting | Default | Prod Value | Rationale |
|---|---|---|---|
| `db_pool_size` | 10 | 10 | One connection per Uvicorn worker; 4 workers × 10 = 40 base connections per pod |
| `db_max_overflow` | 20 | 20 | Burst headroom for concurrent analyze requests (up to 30 connections per pod) |
| `db_pool_timeout` | 30 | 30 | Fail fast if pool exhausted; Sentry alert triggers |
| `db_pool_recycle` | 1800 | 1800 | Recycle before RDS `idle_in_transaction_session_timeout` (300s) |

**Per-pod ceiling**: 30 connections × 10 max replicas = 300 app connections.
PgBouncer multiplexes these into 25 persistent RDS connections.

### PgBouncer (`infra/pgbouncer.ini`)

| Setting | Value | Rationale |
|---|---|---|
| `pool_mode` | transaction | Multiplex short-lived connections; no idle-session waste |
| `default_pool_size` | 25 | 25 persistent RDS connections per database |
| `min_pool_size` | 5 | Keep 5 warm connections for low-latency first-request |
| `reserve_pool_size` | 5 | 5 extra connections for burst (total max: 30) |
| `reserve_pool_timeout` | 3 | Only borrow reserve after 3s wait |
| `max_client_conn` | 1000 | Accept up to 1000 app connections (multiplexed to 30 DB) |
| `server_idle_timeout` | 600 | Close idle DB connections after 10 min |
| `server_connect_timeout` | 5 | Fail fast on DB unavailability |

**Capacity formula**:
```
max_sustained_rps = default_pool_size × queries_per_connection_per_sec
                  = 25 × 10 (avg query ~100ms) = 250 RPS per PgBouncer
```
With 2 replicas behind the ALB: 250 × 2 = 500 RPS sustained (meets target).

### Redis Connection Pool

| Setting | Value | Rationale |
|---|---|---|
| Connections per pod | 50 | Celery broker + event backend + caching |
| Total (10 replicas) | 500 | ElastiCache max is typically 65,000 |

---

## Local Development vs Production

| Aspect | Development | Production |
|---|---|---|
| **Database** | SQLite or local Postgres (`DB_SSL_REQUIRED=false`) | RDS with TLS, PgBouncer (transaction pooling) |
| **Redis** | `redis://localhost:6379` | ElastiCache `rediss://` with AUTH token |
| **Neo4j** | Local Docker container | Neo4j Aura or self-managed cluster |
| **Kafka** | Local Docker (single broker) | Redpanda cluster (3+ nodes) |
| **ML model** | In-process ONNX (loaded from `ml/artifacts/`) | Remote inference service via `MODEL_SERVICE_URL` |
| **Secrets** | `.env` file | AWS Secrets Manager via `SECRETS_MANAGER_PREFIX` |
| **PII encryption** | `PII_ENCRYPTION_KEY` (dev key) | AWS KMS envelope encryption |
| **Events** | Redis Streams (`EVENT_BACKEND=redis`) | Redpanda (`EVENT_BACKEND=kafka`) |
| **Auth** | JWT with short-lived tokens | JWT + refresh tokens, HTTPS-only cookies |
| **Celery** | `CELERY_TASK_EAGER=true` (sync execution) | Broker-backed with dead-letter queue |
| **SSL/TLS** | Not required | Required for DB, Redis, HTTPS ingress |
| **Rate limits** | Generous (default values) | Tuned per endpoint (`RATE_LIMIT_*`) |
| **Monitoring** | Local logs only | OTel → Grafana Tempo/Loki/Prometheus + Sentry |
| **Migrations** | `alembic upgrade head` (auto on startup) | Argo CD sync triggers migration job |
| **Workers** | Single Uvicorn worker | 4 Uvicorn workers per pod |
| **Replicas** | 1 | min 2, max 10 (HPA) |

---

## Migration Paths

### Kafka → Redpanda
Redpanda is wire-compatible with Kafka. To migrate:
1. Deploy Redpanda cluster
2. Update `KAFKA_BOOTSTRAP_SERVERS` to Redpanda endpoints
3. No code changes needed — `kafka-python` client works with Redpanda

### k3s → EKS
1. Export k3s workloads: `kubectl get deployments -o yaml > manifests.yaml`
2. Create EKS cluster in `ap-south-1`
3. Apply manifests with updated environment variables
4. Install Argo CD and configure GitOps sync

---

## Secrets Management

Use Doppler or AWS Secrets Manager. Never store secrets in `.env` or ConfigMaps.
The app bootstraps secrets via `SECRETS_MANAGER_PREFIX` before `Settings()` is created
(`backend/app/services/security/secrets_loader.py`).

## Data Residency

All infrastructure MUST be in `ap-south-1` (Mumbai) for RBI compliance.

## Helm Chart

```bash
# Install
helm install trustshield infra/helm/trustshield/ \
  --set env.DATABASE_URL=<secret> \
  --set env.REDIS_URL=<secret>

# Upgrade
helm upgrade trustshield infra/helm/trustshield/
```

## Load Testing

```bash
# Start load test stack
docker-compose -f infra/docker-compose.loadtest.yml up -d

# Run Locust (web UI at http://localhost:8089)
locust -f backend/tests/load/test_analyze.py --host=http://localhost:8000

# Headless mode
locust -f backend/tests/load/test_analyze.py --host=http://localhost:8000 \
  --headless -u 500 -r 50 --run-time 5m
```

Three weighted user classes:
- **AnalyzeUser** (weight 60): `POST /api/v1/analyze`
- **WebhookUser** (weight 30): `POST /api/v1/webhook/pre-transaction`
- **BatchUser** (weight 10): `POST /api/v1/analyze/batch` (5 items per request)
