# TrustShield — Improvement & Modernization Plan

> Status: **Planning document — no code changes.**
> Scope: Re-architect backend, ML, frontend UI/UX, data layer, DevSecOps, and add net-new high-value functionality using the latest (2025/2026) best-in-class stack.
> Target outcome: A production-grade, real-time fraud-detection platform that is explainable, observable, scalable, and genuinely useful end-to-end.

---

## 0. Current State Assessment (What exists today)

After a full read of the codebase, here is an honest summary of where the project stands:

**Backend (FastAPI / Python 3.11)**
- Router structure is reasonable: `analyze`, `scan`, `webhook`, `report`, `analytics`, `intel`, `recovery`, `auth`, `feedback`, `batch`, `explain`, `behavioral`, `voice`, `image_analysis`, `hotspots`, `ws_dashboard`.
- NLP pipeline exists but is **rule-based keyword matching** (`ScamClassifier` falls back to a hard-coded keyword dict; `_load_model` never actually instantiates the ONNX session even when the file is present).
- Risk scoring is a static 4-factor weighted sum (35/25/20/20).
- Synchronous SQLAlchemy (`create_engine` + `QueuePool`) inside an async FastAPI app — every DB call blocks the event loop.
- Duplicate router includes in `main.py` (feedback/explain/batch/ws are registered twice).
- CORS allows only `GET`/`POST` — blocks legitimate `PUT`/`PATCH`/`DELETE` for the recovery status updates.
- Kafka consumer is a stub that only logs.
- Webhook risk logic is trivial (self-transfer + amount > 50k) and not wired to the entity graph.
- `sync_db` style hardcoded connection strings and no migrations discipline (Alembic present but barely used).

**Frontend (Next.js 14 / React 18 / Tailwind)**
- Dark, single-color, custom-Tailwind-token UI. Hardcoded mock data dominates the dashboard (`scansToday: 145023`).
- No design system, no shared layout shell, no sidebar navigation — every page re-implements its own header.
- Auth handled via `localStorage` token + a permissive middleware that **never actually blocks** anything.
- API client is a thin fetch wrapper with no retry, no cache, no typed error handling, no SWR/React-Query.
- No mobile responsiveness testing, no theming, no accessibility (a11y) consideration, no i18n despite the product being bilingual EN/HI.

**Data Layer**
- PostgreSQL + pgvector, Neo4j, Redis, Kafka, MinIO declared in `docker-compose.yml`.
- pgvector is configured but **not used anywhere** (no embeddings stored or queried).
- No caching layer is actually used at runtime (Redis declared but untouched in the hot path).
- No time-series store for the analytics that the dashboard pretends to render.

**ML**
- `train.py` is a TF-IDF + LogisticRegression baseline on ~50 synthetic templates. ONNX export is optional and never loaded at inference time. No evaluation harness, no model registry, no drift detection.

**DevSecOps / Observability**
- No CI. `prometheus-client` is a dependency but **no `/metrics` endpoint is exposed**.
- No tracing (OpenTelemetry), no structured JSON logging for prod, no error tracking (Sentry).
- No secrets management — secrets sit in `.env` files committed as `.example`.
- No load tests that actually run in CI.

---

## 1. Guiding Principles

1. **Latency budget first** — every architectural choice must protect the <300 ms P95 detection SLA.
2. **Explainability by default** — every score must ship with its contributing factors and SHAP-style attributions.
3. **Defense in depth** — rate-limit, WAF, mTLS for bank integrations, signed webhooks, audit-grade logging.
4. **Async end-to-end** — async DB driver, async Redis, async HTTP, async Kafka — no blocking in the event loop.
5. **Progressive enhancement** — UI works on low-end Android browsers (the primary user device in India).
6. **Bilingual-first** — EN/HI parity everywhere; never an English-only afterthought.
7. **Trunk-based, continuously tested** — every PR must pass contract + integration + load gates.

---

## 2. Target Technology Stack (2025/2026 best-in-class)

| Layer | Current | Proposed | Why |
|---|---|---|---|
| **Language** | Python 3.11 | **Python 3.12** | Performance, exception groups, faster startup |
| **Web framework** | FastAPI | **FastAPI + Litestar comparison** — keep FastAPI, upgrade to latest | Mature, typed, OpenAPI-native |
| **ASGI server** | uvicorn | **Granian** (Rust-based) or Uvicorn with uvloop | ~2–3× throughput |
| **DB driver** | psycopg2 (sync) | **psycopg 3 async** (`psycopg.AsyncConnection`) via SQLAlchemy 2.0 async | True async, no thread-pool blocking |
| **ORM** | SQLAlchemy 1.x-style | **SQLAlchemy 2.0 async + Alembic** migrations, enforced in CI | Type-safe, async-native |
| **Migrations** | `create_all` | **Alembic autogenerate**, migration tests, expand–contract pattern | Safe prod rollouts |
| **Cache** | Redis (unused) | **Redis 7 + redis-py async + `cashews`** for declarative caching | Sub-ms hot reads |
| **Graph DB** | Neo4j | **Memgraph** (in-memory, drop-in Cypher) for hot path + Neo4j for cold storage | 10× faster graph traversal |
| **Queue / streaming** | Kafka (stub) | **Redpanda** (Kafka-compatible, no ZooKeeper, no JVM) | Single binary, ops-friendly |
| **Vector store** | pgvector (unused) | **Qdrant** (dedicated, HNSW-tuned) **or pgvector with ivfflat** — pick one and actually use it | Semantic scam similarity |
| **Object storage** | MinIO | MinIO (keep) + **S3-compatible lifecycle policies** | Evidence/PCAP retention |
| **Time-series** | none | **ClickHouse** or **TimescaleDB** | Sub-second dashboard aggregations |
| **ML serving** | ONNX (unloaded) | **NVIDIA Triton** or **BentoML** + **ONNX Runtime** for the transformer | Dynamic batching, GPU |
| **ML training** | scikit-learn | **Hugging Face Transformers + Datasets + Accelerate**; track with **MLflow** | IndicBERT/MuRIL fine-tuning |
| **Feature store** | none | **Feast** (online + offline) | Consistent train/serve features |
| **LLM layer (new)** | none | **Gemini / GPT-4o via OpenRouter** for narrative explanations + **local Llama 3.1 8B** for sensitive PII text | Adaptive explanations, on-prem fallback |
| **STT (voice)** | none | **WhisperX** (batched) / **Deepgram Nova-3** (streaming) | Real-time vishing on calls |
| **Frontend framework** | Next.js 14 | **Next.js 15 (App Router, RSC, Turbopack, Partial Prerendering)** | Faster, RSC by default |
| **UI library** | raw Tailwind | **shadcn/ui + Radix + Tailwind v4** + **lucide-react** icons | Accessible, themeable, copy-paste components |
| **Charts** | recharts | **Tremor** (built on Recharts) for dashboards + **visx/d3** for the graph viz | Pro fintech look |
| **State / data fetching** | none | **TanStack Query v5** + **Zustand** for UI state | Cache, retry, optimistic |
| **Forms** | raw | **React Hook Form + Zod** (shared with backend via `zod-openapi`) | Typed end-to-end |
| **Auth** | custom JWT | **Clerk** (hosted) **or** self-host **Keycloak/Lucia** with **Better-Auth** | MFA, SSO for banks |
| **i18n** | none | **next-intl** with EN/HI message catalogs | True bilingual |
| **Testing (FE)** | none | **Vitest + Playwright + Testing Library + Storybook** | Unit/E2E/visual |
| **Testing (BE)** | pytest | **pytest + pytest-asyncio + schemathesis** (OpenAPI fuzzing) + **Locust** (load) | Contract + perf |
| **Observability** | none | **OpenTelemetry → Grafana Tempo/Loki/Prometheus + Sentry** | Traces, logs, metrics |
| **CI/CD** | none | **GitHub Actions + Trunk-based + Renovate** | Automated, secure |
| **Containers** | Docker | **Docker + Kubernetes (k3s for dev, EKS/GKE for prod) + Helm** | Scale, self-heal |
| **IaC** | docker-compose | **Pulumi (TypeScript)** or **Terraform** | Reproducible infra |
| **Secrets** | .env | **Doppler / AWS Secrets Manager + SOPS** | Rotation, audit |
| **Feature flags** | none | **PostHog / Unleash** | Safe rollouts |

---

## 3. Architecture Target (To-Be)

```
                         ┌──────────────────────────────────────────────┐
   Banks / SDK / Bot ──▶ │  Edge: Cloudflare WAF + mTLS + Rate-limit    │
                         └──────────────────────┬───────────────────────┘
                                                ▼
                         ┌──────────────────────────────────────────────┐
                         │  FastAPI (Granian) — async, OpenTelemetry    │
                         │  • analyze • scan • webhook • voice(WS)      │
                         │  • explain • intel • recovery • behavioral   │
                         └───┬───────────┬───────────┬──────────┬───────┘
                             │           │           │          │
                  ┌──────────▼──┐  ┌──────▼─────┐ ┌───▼────┐ ┌───▼────────┐
                  │ NLP Service │  │ Graph Svc  │ │ Vector │ │ Feature    │
                  │ (Triton +   │  │ (Memgraph) │ │(Qdrant)│ │ Store      │
                  │  IndicBERT) │  │            │ │        │ │ (Feast)    │
                  └──────────┬──┘  └────────────┘ └────────┘ └────────────┘
                             │
                  ┌──────────▼──────────────────────────────────┐
                  │ Redpanda (events) ─▶ Workers (Celery/Arq)   │
                  │   • audit • alerts • graph-build • retrain  │
                  └──────────┬──────────────────────────────────┘
                             │
        ┌────────────────────┼────────────────────┬──────────────┐
        ▼                    ▼                    ▼              ▼
   PostgreSQL 16       ClickHouse          Redis 7         S3 / MinIO
   (psycopg 3 async)   (analytics)         (cache)         (evidence)
                             │
                  ┌──────────▼───────────────┐
                  │ Observability: OTel →     │
                  │ Tempo / Loki / Prometheus │
                  │ + Sentry + MLflow         │
                  └──────────────────────────┘
```

Key invariants:
- **Hot path is fully async and cached** — Postgres is not on the P95 critical path for repeat lookups (Redis/Memgraph serve them).
- **Heavy ML is off the request path** — Triton is called via async gRPC with a 50 ms timeout; if it times out, fall back to the lightweight distilled classifier so the SLA holds.
- **All side effects are published to Redpanda** and consumed by workers (graph build, alerting, audit, retraining) — the API never blocks on them.

---

## 4. Backend Modernization Plan

### 4.1 Application bootstrap & hygiene
- **Remove the duplicate router includes** in `app/main.py` (feedback/explain/batch/ws registered twice — line 36–39 vs 197–200).
- **Lifespan**: replace `init_db()` (which calls `create_all`) with an **Alembic upgrade-head** gate plus connection-pool warmup. Fail fast if migrations are pending.
- **Fix CORS**: allow the full verb set (`GET, POST, PUT, PATCH, DELETE, OPTIONS`) and read origins from config with regex support.
- **Centralized error envelope**: single `AppError` hierarchy → consistent `{error, detail, code, trace_id}` JSON. Map Pydantic `ValidationError` to 422 with field-level messages.
- **Request validation**: every router uses `Annotated[...]` typed dependencies; deprecate the hand-written `verify_api_key` in favor of **FastAPI security schemes + scopes**.

### 4.2 Async data layer
- Swap `psycopg2-binary` for **`psycopg[binary,pool]` v3** and switch `database.py` to **`create_async_engine` + `async_sessionmaker`**.
- Convert every endpoint to `async def` with `AsyncSession`; introduce `get_async_db()` dependency.
- Introduce **read-replica routing** for analytics endpoints (`/analytics/*`, `/intel/stats`) via a `@use_replica` dependency.
- Add **`pgvector`** or migrate to **Qdrant** for entity embeddings (see §6).

### 4.3 Caching strategy
- Add `cashews` decorators: `@cache(ttl="60s")` on `lookup_entity`, `@early_ttl` on `get_dashboard_stats`, `@locked` on writes.
- Cache key includes a **schema version** so deploys bust the cache safely.
- Use Redis **streams** for the live dashboard fan-out instead of in-process `set()` of WebSockets (so it works across multiple API replicas).

### 4.4 NLP / scoring service rewrite
- Replace `ScamClassifier` keyword fallback with a **two-tier model**:
  1. **Tier-1 (fast, <20 ms):** distilled DistilBERT/IndicBERT quantized → ONNX, served by Triton with dynamic batching.
  2. **Tier-2 (deep, optional):** MuRIL-large for borderline cases (risk in 30–70 band) — runs async, may post-update the score via Redpanda.
- `RiskScorer` becomes **feature-driven**: read features from Feast (entity history, graph centrality, device velocity, geo-anomaly) instead of the 4 hard-coded weights. Make weights themselves configurable & versioned (stored in a `model_params` table tagged by `model_version`).
- Every risk response includes **`explanation`** (top-k SHAP attributions) and **`model_version`** for audit.

### 4.5 Webhook hardening
- Replace the toy self-transfer logic with a **rules engine** (chain of `Rule` objects, each contributing a score + reason) covering: amount velocity, geo-velocity, device fingerprint reputation, mule-account graph signature, beneficiary age, time-of-day, prior VPA disputes.
- **HMAC-signed webhooks** (X-TrustShield-Signature) + idempotency keys.
- Publish every decision to `webhook_decisions` topic → ClickHouse for SLA & dispute analytics.

### 4.6 Graph service
- Use **Memgraph** (or Neo4j with proper indexing) for runtime lookups; run **community detection (Louvain/Leiden)** offline to flag fraud rings and write `ring_id` back as a node property.
- Add **risk-propagation** (Personalized PageRank seeded from blacklisted entities) computed nightly and cached in Redis for sub-ms reads.
- Expose a `/graph/visualize?entity=...` endpoint returning a Cytoscape-compatible JSON for the new graph explorer UI.

### 4.7 Voice & behavioral
- Wire `/voice/stream` to **WhisperX** (local) or **Deepgram Nova-3** (cloud) for real-time transcription with diarization.
- Persist behavioral signals into ClickHouse; train a small gradient-boosted model on them (XGBoost) to produce the `behavioral_risk_score` instead of the current hand-weighted sum.

### 4.8 Recovery & compliance
- Make `recovery/{case_id}` endpoints truly RESTful (`PATCH` for status updates), fix the CORS verb issue that currently blocks them.
- Integrate **real 1930 / cybercrime.gov.in** submission (or a sandboxed mock with a toggle) and store the reference number on the case.
- Auto-generate **RBI quarterly PDFs** with `weasyprint` + HTML templates (replace reportlab) for branded, accessible reports; expose `/reports/rbi/{quarter}` with signed URLs from MinIO.

### 4.9 Background workers
- Migrate from Celery to **Arq** (async, Redis-backed) OR keep Celery with **`celery[asyncio]`-friendly patterns** — pick Arq for greenfield alignment with the async stack.
- Worker responsibilities: graph build, ring detection, alert fan-out (Slack/Email/PagerDuty/WhatsApp), nightly retraining trigger, PDF generation, ClickHouse rollups.

---

## 5. ML & Data-Science Plan

### 5.1 Dataset
- Curate a **real labeled corpus** (open Indian scam-SMS datasets + synthetic augmentation via LLMs for the long tail) targeting ≥ 50k examples across all scam types + balanced legitimate class.
- Maintain an **evaluation gold set** (held-out, manually reviewed) that never enters training — used as the CI gate.

### 5.2 Modeling
- **Primary:** fine-tune **IndicBERT** / **MuRIL** for multi-label scam classification (scam-type + severity head).
- **Secondary:** train a **gradient-boosted model on engineered features** (entity counts, graph centrality, behavioral signals, temporal features) — ensemble with the transformer for the final risk score.
- **Calibration:** apply **isotonic regression** so the model's `confidence` is a true probability — critical for the intervention thresholds.

### 5.3 MLOps
- **MLflow** for experiment tracking + **model registry** (Staging → Production stages).
- **Continuous evaluation**: every PR that touches model code runs the gold-set eval and blocks on F1/precision/recall regression.
- **Drift detection**: population stability index (PSI) on input features + prediction distribution, alerting when PSI > 0.2.
- **Shadow deployments**: new model serves in shadow mode (logged, not returned) for 7 days before promotion.
- **Champion/challenger** with bandit-based traffic split.

### 5.4 Feedback loop
- The `/feedback` endpoint feeds a **weekly retraining pipeline** that promotes a new model only if it beats the champion on the gold set **and** reduces the measured false-positive rate from analyst labels.

### 5.5 Vector search for scam similarity
- Embed every incoming message with a sentence-transformer; query Qdrant/pgvector for **k-nearest known scams**. If top-k similarity > 0.92 and the neighbor was confirmed-fraud, boost the score — this catches paraphrased/evolved scam scripts the keyword model misses.

---

## 6. Frontend / UI Rebuild Plan

Goal: turn the current single-tone dark prototype into a **professional, bilingual, accessible fintech console** with a real design system.

### 6.1 Design system
- Adopt **shadcn/ui + Radix + Tailwind v4** with a **token-driven theme** (light/dark + a "high-contrast" accessibility mode).
- Establish a **TrustShield brand kit**: logo, type scale (Inter + Noto Sans Devanagari for HI), color tokens with WCAG-AA contrast, spacing scale, motion tokens.
- **Storybook** to document and visually-regression-test every component.

### 6.2 Information architecture & navigation
- Introduce a shared **`AppShell`** (sidebar + topbar) used by all authenticated pages instead of per-page headers.
- Sidebar sections:
  1. **Overview** (live dashboard)
  2. **Investigate** (sessions list + detail, entity lookup, graph explorer)
  3. **Scan** (consumer message scanner, voice live monitor, image/QR analyzer)
  4. **Intelligence** (cross-bank network, hotspots map, top entities)
  5. **Recovery** (case queue, complaint drafts)
  6. **Explainability** (model card, factor explorer, drift dashboard, feedback inbox)
  7. **Compliance** (RBI reports, audit log, 1930 submissions)
  8. **Admin** (users/roles, API keys, banks, feature flags)

### 6.3 Page-by-page rebuild

**Overview (Dashboard)**
- Replace hardcoded mock numbers with **TanStack Query** against `/analytics/overview` with a 15 s SWR refresh + a "live" toggle (Redpanda→Redis stream → SSE).
- Add: latency P50/P95/P99 sparkline, intervention-action funnel, top scams ticker, on-call analyst banner, system-status chips (API/DB/Graph/Model).

**Investigate → Sessions**
- New: searchable, filterable **session table** (risk level, scam type, entity, time, analyst verdict) with server-side pagination.
- **Session detail drawer**: full message thread with per-message risk highlight, entity chips, explanation panel, "Mark FP/FN" button (writes to `/feedback`).

**Investigate → Graph Explorer**
- New: interactive **Cytoscape.js** force-directed graph of entities and their connections, color-coded by risk; click a node → side panel with reports, scam types, ring membership.

**Scan**
- Keep the consumer chat scanner but redesign as a **card-based wizard** with sample chips, live risk meter (gauge), bilingual warnings side-by-side, and a "Why?" accordion pulling from `/explain`.
- Add **voice live monitor** (mic → Whisper → streaming risk) and **image/QR analyzer** (upload → OCR + QR decode → entity extraction).

**Intelligence**
- **Cross-bank network** page: stats, recent shared entities, "report a fraudster" form.
- **Hotspots**: India map (choropleth) of fraud density by state/pincode using `react-simple-maps` + ClickHouse geo aggregation.

**Recovery**
- **Case queue** (Kanban by status) + **case detail** with the checklist, auto-filled complaint draft (downloadable PDF), deadline countdown, helpline quick-dial.

**Explainability**
- **Model card** (version, training data summary, gold-set metrics, last promoted-at).
- **Factor explorer**: paste text → see SHAP waterfall of contributions.
- **Drift dashboard**: PSI charts, prediction-distribution histogram, alert history.
- **Feedback inbox**: triage analyst FP/FN labels, approve for retraining.

**Compliance**
- RBI report browser (quarter selector → signed PDF), **immutable audit-log viewer** with hash-chain verification, 1930 submission log.

**Auth**
- Rebuild login/register with **React Hook Form + Zod**, add **MFA (TOTP)**, "magic link", and SSO buttons (Google/Microsoft) via Clerk/Lucia.
- Replace the permissive `middleware.ts` with one that **actually validates** the session cookie (httpOnly) and redirects unauthenticated users.

### 6.4 Cross-cutting FE concerns
- **i18n** with `next-intl`: every string in `messages/en.json` + `messages/hi.json`; language toggle persisted in cookie.
- **a11y**: keyboard nav, focus traps (Radix), aria-live for the live feed, color-contrast ≥ AA, reduced-motion support.
- **Performance**: RSC for static shells, `next/dynamic` for charts, edge runtime for the scanner page, Lighthouse CI gate (perf ≥ 90).
- **Offline-tolerant scanner**: the consumer scanner works via a PWA + service worker so rural users on flaky networks can paste and scan.
- **Real-time**: replace the WS-with-mock-fallback pattern with **SSE from Redpanda** through an authenticated edge endpoint; mock only when explicitly in "demo mode" (visible badge).

---

## 7. New High-Value Functionality (Net-new)

1. **Consumer mobile PWA + WhatsApp bot** — let end-users forward a suspicious message and get a bilingual risk verdict + recovery steps; the existing `/scan-message` becomes the backend for this.
2. **Fraud-ring auto-detection** — nightly graph algorithms surface connected mule clusters and file them as cases for analysts.
3. **Adaptive bilingual warnings** — an LLM (Gemini/GPT-4o, with on-prem Llama fallback) rewrites the canned warnings into context-aware, regional-language messages (Marathi/Tamil/Bengali) tuned to the victim's locale.
4. **Coached-victim intervention** — when behavioral signals + NLP both fire, trigger an in-app "cool-off" (10-min transaction freeze) and a callback from the partner bank.
5. **Merchant/VPA reputation API** — public `GET /reputation/{vpa}` returning a 0–100 score + report count, monetizable as a paid tier and embeddable as a widget.
6. **Banker dashboard (B2B)** — separate role-scoped UI for partner banks showing their own flagged sessions, dispute status, and SLA adherence.
7. **Regulator export pack** — one-click RBI/1930 quarterly bundle (PDF + CSV + signed manifest).
8. **Model explainability chat** — analysts ask "why was session X flagged?" in natural language; the LLM answers from the stored explanation + graph context (RAG).
9. **Threat-intel ingest** — consume public blocklists (HaveIBeenPwned-style, RBI advisories, CERT-In) and auto-merge into the entity graph.
10. **SDK hardening** — Android SDK gains Play Integrity API + SafetyNet attestation, sends device-fingerprint + behavioral signals, and supports silent background scanning of SMS (with user consent).

---

## 8. Security & Compliance

- **AuthN/Z**: JWT access (15 min) + rotating refresh; **RBAC** (analyst/admin/bank/read-only) enforced at route + data level; **ABAC** for tenant isolation (banks see only their data).
- **mTLS** for all bank-to-TrustShield traffic; **HMAC signatures** on every webhook in and out.
- **PII handling**: the existing `app/utils/pii.py` becomes a real **redaction pipeline** — phone/UPI/IFSC are tokenized before logging or LLM calls; raw values encrypted at rest (AES-GCM, keys in KMS).
- **Audit**: every state-changing call writes an **append-only, hash-chained** record to the `audit_log` (existing `AuditLog` model) and to ClickHouse; tamper-evident via chained SHA-256.
- **Data residency**: all data stays in India (Mumbai region); document this for RBI compliance.
- **OWASP Top 10 + API Top 10**: automated **ZAP** + **schemathesis** scans in CI; **Snyk** for deps; **Trivy** for images; **gitleaks** for secrets.
- **Rate limiting & DDoS**: Cloudflare at the edge + `slowapi` per-route; separate quotas per API-key tier.
- **GDPR/DPDP Act 2023**: right-to-access and right-to-erasure endpoints for end-users; data-retention policy enforced by ClickHouse/Postgres TTL.

---

## 9. Observability & SLOs

- **OpenTelemetry** instrumentation across HTTP, DB, Redis, Kafka, Triton; traces exported to **Tempo**, logs to **Loki**, metrics to **Prometheus**.
- **SLOs** with error budgets:
  - Detection latency P95 < 300 ms (hot path), P99 < 500 ms.
  - Availability 99.9% for `/analyze` and `/webhook/pre-transaction`.
  - Model precision ≥ 0.92 on the gold set; false-positive rate ≤ 2%.
- **Dashboards**: Grafana boards for latency heatmap, intervention-action funnel, model confidence distribution, graph-query latency, worker lag.
- **Alerting**: Alertmanager → PagerDuty (P1), Slack (#trustshield-ops). Alerts on SLA burn, model drift, Kafka consumer lag, DB pool saturation.
- **Sentry** for FE + BE error tracking with release health and session replay.

---

## 10. DevSecOps & CI/CD

- **GitHub Actions matrix**:
  - `lint` (ruff + eslint + prettier)
  - `typecheck` (mypy + tsc)
  - `unit` (pytest, vitest)
  - `contract` (schemathesis against OpenAPI)
  - `integration` (docker-compose stack + pytest)
  - `load` (Locust, nightly on staging)
  - `security` (trivy, gitleaks, snype, ZAP)
  - `model-eval` (gold-set gate)
  - `build-push` (multi-arch images to GHCR)
- **Trunk-based** with short-lived branches; **Renovate** for deps; **required reviews** + **CODEOWNERS**.
- **Environments**: `dev` (k3s local) → `staging` (EKS) → `prod` (EKS) with **Argo CD** GitOps and **progressive delivery** (Argo Rollouts: 10% → 50% → 100% with automated metric analysis).
- **Feature flags** (PostHog/Unleash) for every user-visible change; dark-launch by default.
- **Database migrations**: expand–contract, **reversible**, run in CI against a clone; migration review checklist.

---

## 11. Implementation Phases (Roadmap)

Each phase ends with a **deployable, demoable** increment.

### Phase 0 — Stabilize (Week 1–2)
- Kill duplicate router includes; fix CORS verbs; centralize error envelope.
- Switch to psycopg 3 async + SQLAlchemy 2.0 async; introduce Alembic as the source of truth.
- Add OpenTelemetry + Sentry + `/metrics`; fix the silent mock-fallback on the dashboard (badge "demo mode").
- **Exit gate:** staging deploy with real DB, traces visible in Tempo, dashboards show live (non-mock) data.

### Phase 1 — Real ML (Week 3–6)
- Build the labeled corpus + gold set; fine-tune IndicBERT; serve via Triton.
- Rewrite `ScamClassifier` + `RiskScorer` to be feature-driven and versioned; add SHAP explanations.
- Add MLflow registry, shadow-mode deploy, drift monitoring.
- **Exit gate:** gold-set F1 ≥ 0.90, P95 latency < 300 ms with Triton in the loop.

### Phase 2 — Frontend Rebuild (Week 4–8, parallel)
- Stand up shadcn/ui design system + Storybook + AppShell.
- Rebuild Overview, Investigate (sessions + detail), Scan pages first; wire TanStack Query.
- Add i18n (EN/HI), a11y pass, Lighthouse gate.
- **Exit gate:** all primary flows usable, Lighthouse ≥ 90, no mock data on core pages.

### Phase 3 — Graph + Intelligence (Week 7–10)
- Memgraph + risk propagation + ring detection; Graph Explorer UI.
- Cross-bank intel hardening; threat-intel ingest; hotspots map.
- **Exit gate:** a real fraud ring surfaced end-to-end from data → graph → UI → case.

### Phase 4 — Voice, Behavioral, Recovery (Week 9–12)
- WhisperX/Deepgram streaming voice; behavioral model trained on ClickHouse data.
- Recovery case queue + auto-complaint + 1930 sandbox; RBI PDF generator.
- **Exit gate:** live voice vishing detection demo; recovery PDF export.

### Phase 5 — Scale & Compliance (Week 11–14)
- Redpanda + Arq workers; Redis-stream fan-out for multi-replica dashboards; read replicas.
- mTLS + HMAC + RBAC/ABAC; audit hash-chain; DPDP endpoints.
- k3s→EKS + Argo CD + progressive delivery.
- **Exit gate:** load test of 1k RPS on `/analyze` holding SLA; SOC2-style audit log verifiable.

### Phase 6 — New Products (Week 13+)
- Consumer PWA + WhatsApp bot; merchant reputation API; banker dashboard; explainability chat; SDK hardening.

---

## 12. Success Metrics (KPIs)

| Area | Metric | Target |
|---|---|---|
| Performance | `/analyze` P95 latency | < 300 ms |
| Performance | `/webhook/pre-transaction` P95 | < 100 ms |
| ML quality | Gold-set macro-F1 | ≥ 0.90 |
| ML quality | Production false-positive rate | ≤ 2% |
| Reliability | `/analyze` availability | 99.9% |
| Adoption | Sessions analyzed / day | ramp to 1 M |
| Trust | Analyst-labeled precision | ≥ 0.92 |
| Compliance | Audit-log tamper verification | 100% pass |
| UX | Lighthouse (perf/a11y) | ≥ 90 / ≥ 95 |
| UX | Time-to-verdict on consumer scanner | < 3 s |

---

## 13. Risks & Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Model latency blow-up from Triton | SLA miss | Two-tier fallback; circuit breaker to distilled model |
| LLM cost for adaptive warnings | $$ | Cache + on-prem Llama fallback; only call for borderline cases |
| Graph DB saturation at scale | Slow lookups | Memgraph in-memory + PageRank precompute in Redis |
| PII leakage to LLM providers | Compliance breach | Redact before any external call; on-prem model for sensitive text |
| False positives erode trust | Customer churn | Calibration + analyst feedback loop + FP rate SLO |
| Multi-tenant data leakage | Security incident | Row-level tenant policies + automated tests + ABAC enforcement |
| Migration downtime | Prod incident | Expand–contract + Blue/Green + reversible Alembic |

---

## 14. Out of Scope (Explicit Non-Goals for v2)

- Building a native iOS app (PWA first; iOS SDK later).
- Crypto-wallet fraud (UPI/card/voice focus for now).
- Replacing FastAPI with a different framework (Litestar eval only).
- Self-hosting the LLM training stack (use managed HF endpoints where sensible).

---

## 15. Definition of Done (for the whole effort)

- Every endpoint has contract + integration tests; CI is green on `main`.
- `<300 ms` P95 demonstrated by a published Locust report.
- Gold-set F1 ≥ 0.90 with drift dashboard live.
- UI passes Lighthouse ≥ 90 and a manual a11y audit.
- Audit log is hash-chain verifiable; one RBI quarterly report generated end-to-end.
- Runbook + architecture diagrams + this plan updated to reflect what shipped.

---

*This document is intentionally code-free and decision-oriented. Each section is sized so it can become an epic with tickets derived directly from its bullet points.*
