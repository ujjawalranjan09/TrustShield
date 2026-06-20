# TrustShield — Improvement Plan 2: Business-Production Readiness

> **Status:** Planning document — no code changes.
> **Purpose:** Take the now-functional codebase (Phases 0–4 of `IMPROVEMENT_PLAN.md` implemented, bugs fixed per `BUGFIX_LOG.md` and the 2026-06-19 audit pass) and harden it into a **commercially deployable, compliance-grade, revenue-ready** product.
> **Audience:** Founders, CTO, engineering lead, compliance officer.
> **Horizon:** 8–12 weeks of focused work to go from "works in dev" to "deployed for paying bank customers under RBI/DPPT scrutiny."

---

## 0. Why a Second Plan?

`IMPROVEMENT_PLAN.md` was an **architecture & tech-stack** plan: rebuild the UI, add async DB, add real ML, add graph intelligence. That work is done (or stubbed with graceful fallbacks). The codebase boots, the 18 endpoints in `BUGFIX_LOG.md` return 200, and the bug audit fixed 12 correctness/security issues.

What's **still missing** is everything that separates a demo from a product a bank will pay for and a regulator will accept:

- Real authentication security (tokens in JS-readable cookies today; no refresh rotation; no session revocation).
- Production data persistence (SQLite/ephemeral Postgres today; no backups; no PITR).
- Real ML artifacts (no trained transformer/GBM ONNX checked in; keyword fallback is the live path).
- Monetization surface (no billing, no API tiering, no usage metering).
- Compliance evidence (audit log exists but isn't verified in CI; no DPDP register; no RBI submission proof).
- Operational maturity (no runbook, no on-call, no SLO dashboards, no incident process).
- Customer-facing trust signals (no status page, no SLA contract, no security.txt, no privacy policy).

This plan closes each of those gaps, sequenced so the company can start **selling** after Phase A and **scaling revenue** after Phase B.

---

## 1. Guiding Principles (Business-Grade)

1. **Sellable before scalable.** Land the first paying bank with a single-region, single-replica deployment before engineering for 100× load.
2. **Compliance is a feature, not a gate.** Every security/privacy control produces an **artifact** (log, report, certificate) a regulator or auditor can inspect.
3. **Pay for what you sell.** Usage metering and billing ship **with** the paid feature, not after.
4. **Failure is planned.** Every external dependency (Neo4j, Redis, model server, bank API) has a documented fallback and the fallback is **tested in CI**.
5. **Security by default, obscurity nowhere.** Secrets in a manager; PII tokenized at rest; no internal error details to clients (enforced, not aspirational).
6. **Data residency is contractual.** India-only data storage, documented and verifiable.
7. **Observability before optimization.** You cannot improve what you cannot measure — SLOs and cost telemetry first, perf tuning second.

---

## 2. Current State vs. Business-Production (Honest Gap)

| Dimension | Today (post-bugfix) | Business-Production Target |
|---|---|---|
| **Auth** | JWT in `SameSite=Lax` JS-readable cookie, 15-min access, 7-day non-rotating refresh, no revocation list | httpOnly+Secure cookie, **rotating refresh**, server-side session + **revocation**, optional **TOTP MFA**, SSO for banks |
| **DB** | Postgres via asyncpg, Alembic-managed, single instance | HA Postgres (managed RDS/Aurora), automated daily backups + 35-day PITR, read replica, connection pooling (PgBouncer) |
| **ML** | Keyword fallback is live path; ONNX loader exists but no artifacts checked in; `ModelRegistry` loads defaults | Trained IndicBERT + XGBoost artifacts in MLflow registry, served via Triton/BentoML, **shadow-mode validated**, gold-set F1 ≥ 0.90 in CI gate |
| **Secrets** | `.env` files, `jwt_secret="dev-secret-change-in-production"` default | Doppler/AWS Secrets Manager, **no default secrets**, rotation policy, `gitleaks` in CI |
| **Observability** | OTel + Sentry + `/metrics` wired but unmonitored | Grafana SLO dashboards, PagerDuty alerts, error-budget burn warnings, monthly SLO review |
| **Billing** | None | Stripe-metered billing per API call + tiered plans (Free / Pro / Bank / Enterprise), usage caps, dunning |
| **Compliance** | Audit log + DPDP stubs, hash-chain unverified in CI | SOC 2 Type I in flight, DPDP **data register + DPO contact**, RBI submission receipts persisted, quarterly attestation |
| **Deployment** | `docker-compose`, manual | GitOps (Argo CD) on managed K8s, progressive delivery, automated rollback |
| **Docs** | README + IMPROVEMENT_PLAN | Customer-facing docs site (Mintlify/Docusaurus), API reference from OpenAPI, status page, SLA, security.txt, privacy policy, DPA |
| **Support** | None | In-app chat (Intercom/Crisp), support@ mailbox, on-call rota, incident response runbook, postmortem template |

---

## 3. Phase A — Sellable (Weeks 1–3)

**Goal:** A single bank can sign an MSA, integrate via API key, and trust the platform for production traffic. Revenue-ready.

### A1. Authentication hardening
- **httpOnly + Secure + SameSite=Strict cookies.** The current `SameSite=Lax` cookie is JS-readable via `document.cookie`; move access token to an httpOnly cookie set by a backend `/auth/session` endpoint so client JS can never read it. Keep a non-sensitive `ts_session` indicator cookie for the middleware gate.
- **Refresh-token rotation.** On each `/auth/refresh`, issue a new refresh token and **invalidate the old one** (store a `token_family` + `rotated_at` in a `refresh_tokens` table; reject reuse → revoke the whole family on reuse, a standard refresh-theft defense).
- **Session revocation.** Add a `revoked_sessions` table (or Redis set) checked in `get_current_user`. Logout writes to it. Admin "force logout" writes to it.
- **TOTP MFA** (optional, opt-in) via `pyotp`; enforce for `super_admin` and `bank` roles.
- **Password policy.** Enforce via `RegisterRequest` (min 12 chars, breached-password check via HaveIBeenPwned k-anonymity API, not just min 8).
- **Rate limit `/auth/*`** to `5/minute/IP` and `10/hour/email` to blunt credential stuffing.
- **Remove `jwt_secret` default.** Fail-fast at startup if `settings.jwt_secret == "dev-secret-change-in-production"` and `environment != "development"`.

### A2. Secret management
- Adopt **Doppler** (or AWS Secrets Manager) for all secrets; `.env` only for local dev.
- Add `gitleaks` to CI to reject any secret committed.
- Rotate the JWT secret, DB password, Neo4j password, Redis password as a documented quarterly runbook.
- Replace `X-API-Key` shared-secret bank auth (in `intel.py`) with **per-bank HMAC-signed requests** + rotating API keys stored hashed in the DB (never plaintext).

### A3. Production data layer
- Move off local Postgres to **managed Postgres** (RDS/Aurora/CloudSQL) in Mumbai region (`ap-south-1`).
- Enable **automated daily backups + 35-day point-in-time recovery**; document restore drill (run it once a quarter).
- Add **PgBouncer** in transaction-pooling mode in front of Postgres.
- Add a **read replica**; route `/analytics/*`, `/audit/*`, `/intel/stats` to it via a `@use_replica` dependency.
- Define and enforce **retention** via scheduled jobs: `scan_events` 730 days, `recovery_cases` 7 years, `behavioral_signals` 180 days, `audit_logs` indefinite. (Policies already exist in `config.py` — wire them to actual TTL jobs.)

### A4. Bank onboarding flow
- `/intel/register-bank` today returns an API key in plaintext in the response body. Change to: **show the key ONCE**, store only a **hash** in the DB, support **regeneration** and **revocation**.
- Add `GET /intel/banks/me` so a bank can see its own profile, key fingerprint, and last-used timestamp.
- Add a **partner agreement acceptance** step (legal terms stored with timestamp + version on the `Bank` row) — required for MSA.

### A5. Customer trust surface
- **Status page** (Atlassian Statuspage / Better Stack) — `status.trustshield.in`.
- `security.txt` at `/.well-known/security.txt` with PGP key and vuln-report policy.
- **Privacy policy** + **DPA** (data-processing agreement) pages, versioned.
- **SLA document**: 99.9% `/analyze` availability, P95 < 300ms, credit policy for misses.
- Public **API docs** generated from the OpenAPI schema via Redoc/Mintlify, with a sandbox key.

### A6. Exit gate (Phase A)
- A demo bank can: register → accept terms → get an API key → call `/analyze` and `/webhook/pre-transaction` with rotating keys → see usage → receive an invoice stub.
- All secrets in a manager; no `dev-secret` in any environment.
- Backup restore drill documented.
- Status page live; SLA + privacy policy published.

---

## 4. Phase B — Revenue-Ready (Weeks 3–6)

**Goal:** Charge for usage, prove ML quality, and produce compliance evidence on demand.

### B1. Billing & metering
- **Stripe Billing** with metered usage (per `/analyze` and `/webhook` call) + tiered plans:
  - **Free:** 1k scans/mo, keyword-only model, community support.
  - **Pro:** 50k scans/mo, ML model, email support, 99.5% SLA.
  - **Bank:** 1M scans/mo, webhook integration, SSO, 99.9% SLA, named CSM.
  - **Enterprise:** custom volume, on-prem option, dedicated infra, 99.95% SLA.
- **Usage metering:** every billable call increments a counter in Redis (hourly bucket) + nightly roll-up to Postgres `usage_ledger`. Stripe `Reporting` reads from the ledger.
- **Quota enforcement:** reject calls over plan limit with `429` + `Retry-After` and a metering web hook to nudge upgrade.
- **Dunning & churn:** Stripe handles failed payments; gate API access on subscription status.

### B2. Real ML in production
- **Train and ship the two-tier model** the Phase-1 plan specified: IndicBERT (transformer) + XGBoost (GBM), exported to ONNX, registered in MLflow.
- **Serve via Triton** (or BentoML for cost) behind a 50ms timeout with **graceful fallback** to the keyword classifier (already wired in `classifier.py`).
- **Calibration** with isotonic regression so `confidence` is a real probability (critical for intervention thresholds and for the FP-rate SLA).
- **CI gold-set gate:** any PR touching `ml/` runs the held-out gold set; merge blocked if macro-F1 regresses > 1pt or FP-rate worsens.
- **Drift monitoring:** PSI computed nightly, written to `drift_log` (table exists), surfaced on the Explainability dashboard, paged when PSI > 0.2.
- **Shadow-mode validation:** new model serves in shadow for 7 days before promotion; `ModelRegistry.hot_swap` only runs after the promoter worker confirms gold-set + shadow metrics.

### B3. Compliance evidence pipeline
- **Audit log verification in CI:** a nightly job runs `verify_chain` end-to-end and alerts on any `valid=false`. Today the hash-chain exists but is never verified on a schedule — a broken chain is a silent compliance failure.
- **DPDP register:** maintain a machine-readable data inventory (what PII we hold, where, retention, lawful basis) — required under DPDP §8. Today PII is scattered across `recovery_cases`, `feedback_labels`, `behavioral_signals`, `intel_*` with no central register.
- **RBI submission receipts:** the `cybercrime_sandbox` stub returns a fake reference; wire to the real sandbox (or document the manual fallback) and **persist the receipt** on the `RecoveryCase` so the victim and the bank can prove they filed.
- **Quarterly attestation export:** one-click bundle (PDF + CSV + signed manifest) of: scan volume, FP/FN rates from `feedback_labels`, audit-chain verification report, drift report, incident log. This is the artifact that makes SOC 2 / RBI audits survivable.

### B4. PII & encryption
- **Tokenize PII at rest:** phone, UPI ID, IFSC, email stored as tokens (format-preserving encryption or a vault) in Postgres; raw value recoverable only via a KMS-controlled decrypt path. The `pii.py` utility becomes that path.
- **Field-level encryption** for `recovery_cases.victim_name`, `victim_phone`, `scammer_info`.
- **Encrypted backups** (managed RDS does this by default — verify).
- **PII redaction before any external LLM call** (warnings, explainability chat) — enforce via a single `redact()` chokepoint, tested.

### B5. Exit gate (Phase B)
- First paying customer onboarded with metered billing; invoice generated correctly.
- Gold-set F1 ≥ 0.90, FP-rate ≤ 2%, drift dashboard live.
- Audit-chain verification job green for 30 consecutive days.
- DPDP data register published internally; RBI submission receipt persisted on at least one end-to-end recovery case.

---

## 5. Phase C — Scale & Reliability (Weeks 6–9)

**Goal:** Hold the SLA under real load, survive dependency failures, and operate without the founders on call.

### C1. Production deployment
- **Managed Kubernetes** (EKS/GKE) in Mumbai; **Argo CD** GitOps; **Argo Rollouts** progressive delivery (10% → 50% → 100% with automated metric analysis → auto-rollback on SLA burn).
- **Horizontal autoscaling** on API pods (CPU + custom RPS metric); pre-warm the connection pool and model loader on boot (today `ModelLoader.load()` is lazy — add eager warm in lifespan).
- **Separate worker pool** for Celery (ring detection, risk propagation, threat ingest, PDF gen, drift) with its own autoscaling and dead-letter queue.

### C2. Dependency resilience
- For every external dependency, document and **CI-test** the fallback:
  - Neo4j down → graph enrichment returns zeros (works today via `_ensure_connected`).
  - Redis down → cache misses, direct DB reads (verify `get_entity_risk` degrades correctly).
  - Triton down → keyword classifier (works today).
  - Postgres down → 503 with retry-after (health check already probes DB).
  - Bank webhook target down → retry with exponential backoff + DLQ.
- **Circuit breakers** (via `pybreaker`/`tenacity`) on the model server and graph calls to fail fast instead of piling up timeouts.

### C3. SLOs & error budgets
- Define and dashboard SLOs with **error budgets**:
  - `/analyze` P95 < 300ms, P99 < 500ms, availability 99.9%.
  - `/webhook/pre-transaction` P95 < 100ms, availability 99.95%.
  - Model gold-set macro-F1 ≥ 0.90.
  - Production FP-rate ≤ 2% (measured from `feedback_labels`).
- **Alerting:** PagerDuty P1 on SLA burn or audit-chain break; Slack `#trustshield-ops` for warnings; 30-min ack SLA on P1.
- **Monthly SLO review** with the error-budget gate: if budget exhausted, freeze feature work for reliability.

### C4. Observability maturity
- Grafana dashboards: latency heatmap, intervention funnel, model confidence distribution, graph-query latency, worker lag, DB pool saturation, billing meter lag.
- **Cost telemetry:** tag all cloud resources; daily cost-per-1k-scans metric; alert on cost spike.
- **Structured JSON logging** in prod (today the formatter is text); ship to Loki.

### C5. Operational readiness
- **Runbooks** for the top 10 incidents (DB failover, model server down, audit-chain break, SLA burn, bank integration outage, drift spike, OOM, cert expiry, backup-restore, SEV-1 comms).
- **On-call rota** (PagerDuty schedule) with handoff doc.
- **Incident response process:** severity matrix, comms template (status page + customer email), blameless **postmortem template** with action items tracked to closure.
- **Game days:** quarterly failure injection (kill Neo4j, saturate DB pool, push a bad model) to exercise the runbooks.

### C6. Exit gate (Phase C)
- Load test of 1k RPS on `/analyze` holding the P95 SLA, published as a Locust report.
- Argo CD blue/green deploy with automated rollback demoed.
- 3 consecutive monthly SLO reviews with budget intact.
- One game day completed with postmortem.

---

## 6. Phase D — Enterprise & Growth (Weeks 9–12)

**Goal:** Win enterprise bank deals and expand the product surface.

### D1. Enterprise security
- **SSO/SAML** for banks via Keycloak or WorkOS (today only email/password).
- **SCIM provisioning** so bank IT can manage analyst accounts.
- **mTLS** for all bank-to-TrustShield traffic; client cert validation per bank.
- **Dedicated tenancy option** (separate namespace + DB schema) for the largest banks.
- **Pen test** (annual, third-party) + **bug bounty** (HackerOne private program).
- **SOC 2 Type II** evidence collection automated (continuous control monitoring via Vanta/Drata).

### D2. Product expansion
- **Consumer PWA + WhatsApp bot** (Phase 6 of Plan 1) — the `/consumer/scan` and `/whatsapp/webhook` endpoints exist; ship the PWA and complete the WhatsApp reply send path (today `_send_whatsapp_reply` is commented out).
- **Merchant reputation widget** — `/reputation/{vpa}/widget` exists (SVG); package as an embeddable `<script>` + dashboard for merchants to self-serve.
- **Explainability chat (RAG)** — `/explain/chat` exists; wire the real LLM with PII redaction + retrieval over stored explanations.
- **Banker dashboard B2B** — `/banker/*` exists; add dispute workflow, SLA adherence report, and CSV export.

### D3. Data products
- **Industry fraud-trend reports** (anonymized, aggregated) sold as a subscription to banks and regulators — monetize the intel network data.
- **Threat-intel API** — paid feed of confirmed-bad entities (hashed) for banks to ingest into their own rules engines.
- **Model-as-a-service** — let banks call the ML model directly for their own non-TrustShield flows.

### D4. Exit gate (Phase D)
- One enterprise bank on SSO + mTLS + dedicated tenancy.
- SOC 2 Type II report issued.
- Consumer PWA live with >10k MAU.
- First data-product subscription sold.

---

## 7. Cross-Cutting: What Must Be True Always

These are not phase-gated — they are continuous hygiene:

- **CI is green on `main`** with: lint (ruff/eslint), typecheck (mypy/tsc), unit (pytest/vitest), contract (schemathesis), integration (docker-compose stack), security (trivy/gitleaks/snyk/zap), model-eval (gold-set gate), build (multi-arch images to GHCR).
- **Trunk-based** with short-lived branches, required reviews, CODEOWNERS, Renovate for deps.
- **Every PR description** answers: does this touch PII? does it change the risk score? does it need a compliance review?
- **Definition of Done** (per feature): deployed to staging, SLO dashboards updated, runbook updated, docs updated, billing implications considered, rollback plan known.
- **No mock data in production paths** without an explicit "demo mode" badge visible to the user.

---

## 8. Risk Register (Business, not Technical)

| Risk | Impact | Mitigation |
|---|---|---|
| **Regulator (RBI/DPDP) action** for a data breach | Existential | Tokenize PII, encrypt at rest, audit chain verified daily, breach-notification runbook, cyber-insurance |
| **False positive causes a bank to block a legit transaction** | Churn + lawsuit | FP-rate SLO (≤2%), analyst feedback loop, per-bank tuning, contractual limitation of liability |
| **Model drift** silently degrades detection | Customer trust loss | Nightly PSI, shadow-mode promotion, gold-set CI gate, weekly model review |
| **Single big customer** = revenue concentration | Revenue cliff | Diversify across banks + consumer + data products; contractual minimums |
| **Founders are the only on-call** | Burnout + missed SLA | Phase C on-call rota + game days + documented runbooks |
| **Cost overrun** from LLM/Triton/infra | Margin compression | Cost telemetry (Phase C3), per-tier cost ceiling, on-prem Llama fallback for LLM |
| **Vendor lock-in** (Stripe, Doppler, cloud) | Pricing leverage loss | Abstract behind interfaces; quarterly "exit cost" review |
| **Key-person dependency** on ML/auth knowledge | Bus factor | Pairing, ADRs (architecture decision records), this doc kept current |

---

## 9. Definition of Done (Whole Effort)

- A bank signs an MSA, integrates, and pays an invoice — end to end, without founder intervention on the technical path.
- SOC 2 Type II report issued; DPDP data register maintained; RBI submission receipts persisted.
- SLO dashboards public to customers; monthly review cadence held; error budgets respected.
- Pen test passed; bug bounty live; no `dev-secret` anywhere; backups restorable (drill proven).
- Runbooks for top-10 incidents; on-call rota staffed; one game day + postmortem completed.
- Consumer PWA and at least one data product generating independent revenue.

---

## 10. Sequencing Summary

| Phase | Weeks | Theme | Revenue milestone |
|---|---|---|---|
| **A** | 1–3 | Sellable | First MSA signable; API-key bank onboarding |
| **B** | 3–6 | Revenue-ready | First paid invoice; ML quality proven; compliance artifacts |
| **C** | 6–9 | Scale & reliability | SLA held at 1k RPS; on-call rota live |
| **D** | 9–12 | Enterprise & growth | Enterprise SSO/mTLS deal; consumer + data-product revenue |

---

## 11. Open Decisions (Founders/CTO)

1. **Cloud:** AWS (ap-south-1) vs Azure (Central India) vs self-host — affects compliance posture and cost.
2. **Auth:** Keep custom JWT (cheaper, more control) vs adopt Clerk/WorkOS (faster SSO, more expensive) — recommend WorkOS for SSO, keep custom for consumer.
3. **ML serving:** Triton (GPU, complex) vs BentoML (CPU, simpler) vs managed HF Inference — recommend BentoML until volume justifies Triton.
4. **Compliance cert to chase first:** SOC 2 Type I (faster, ~3mo) vs ISO 27001 (broader recognition, ~6mo) — recommend SOC 2 Type I first, ISO later.
5. **Consumer monetization:** Free PWA as a customer-acquisition loss-leader vs paid premium tier vs ad-supported — recommend free-to-acquire, monetize via banks.

---

## Appendix: Mapping to the Bug Audit (2026-06-19)

The following bugs found in the codebase audit were fixed before this plan was written; they are the **prerequisite** to Phase A:

- `analyze.py` called nonexistent `graph.get_connected_entities` → fixed to `get_neighbors`.
- `FraudEntityGraph` never lazily connected on non-visualize paths → added `_ensure_connected()` to all methods.
- `analyze.py` leaked the Neo4j driver per request → added `finally: await graph.close()`.
- `warning_generator.py` Hindi string contained Chinese characters → fixed.
- `dpdp.py` erasure endpoint wiped ALL users' PII → scoped to authenticated user.
- `dpdp.py` `_get_current_user` always raised 401 (dead code) → replaced with real JWT dependency.
- `feedback.py` / `reputation.py` leaked internal exceptions to clients → generic messages.
- `graph.py /visualize` had a fake auth dependency → real `get_current_user`.
- `alembic/env.py` missing `InterventionLog` import → added.
- Frontend `lib/auth.ts` used `localStorage` while middleware checked cookies → switched to cookies.
- Frontend `middleware.ts` `PUBLIC_PATHS` didn't account for `[locale]` routing → fixed segment matching.

These fixes are the floor. Phase A builds the actual business on top of it.
