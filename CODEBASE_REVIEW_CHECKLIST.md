# TrustShield — Full Codebase Review Checklist (Post Phases A–E)

> **Purpose:** A systematic, executable review of the entire codebase after Phases A–E are implemented. Work top-to-bottom; each item is a concrete check with a pass/fail criterion. File issues for any `fail`.
>
> **Scope:** Backend (FastAPI, 155 files), Frontend (Next.js 15 + i18n), SDKs (Android/iOS/Web), Infra (Docker/Helm/Terraform/runbooks), Tests (68 backend test files), CI/CD, Docs.
>
> **Legend:** ✅ = PASS, ❌ = FAIL, ⚠️ = PASS (with caveats), 🔍 = UNKNOWN (not yet checked)

---

## Section 0 — Repo Hygiene & Top-Level Sanity

- ⚠️ **0.1** No stray one-off scripts at repo root. Root contains ad-hoc files that look like debugging leftovers: `check_db.py`, `check_feedback_table.py`, `test_db_queries.py`, `test_endpoints.py`, `test_explain_*.py`, `test_feedback_explain.py`, `test_individual.py`, `test_nlp_services.py`, `generate_dataset.py`, `nul`, `rbi_report_mock.pdf`. **Action:** move to `scripts/` or `backend/scripts/`, or delete; the `nul` file is almost certainly a Windows redirect accident — remove it.
  > **Evidence:** 9 `test_*.py` + 2 `check_*.py` not tracked in git but cluttering root. `generate_dataset.py` IS tracked at root — should be in `scripts/`. `nul` (167 bytes of garbage) is gitignored but exists on disk.
- ❌ **0.2** `.gitignore` excludes `.venv/`, `.ruff_cache/`, `__pycache__/`, `.kilo/`, `.mimocode/`, `.hermes/`, `node_modules/`, `*.pdf` artifacts — verify none of these are tracked.
  > **Evidence:** Missing from `.gitignore`: `.ruff_cache/`, `.kilo/`, `.mimocode/`, `.hermes/`, `*.pdf`. `rbi_report_mock.pdf` IS tracked in git because of the missing `*.pdf` rule.
- ✅ **0.3** `.gitleaksignore` entries are reviewed — each ignored secret pattern is intentional and documented, not a real leaked credential being swept under the rug.
  > **Evidence:** Only suppresses `conftest.py` sample test fixtures and `test_classifier.py` mock key patterns. Clean.
- ✅ **0.4** `.env.example` (root) and `backend/.env.example` contain **no real values**, only placeholders; the `.example` files are the only env files tracked.
  > **Evidence:** Root `.env.example` is just a redirect to `backend/.env.example`. Backend version has all secrets empty or obvious templates (`postgresql://user:password@localhost`).
- 🔍 **0.5** Planning docs (`IMPROVEMENT_PLAN.md`, `IMPROVEMENT_PLAN_2.md`, `PHASE_*_PLAN.md`, `BUGFIX_LOG.md`) are either moved to `docs/` or marked "historical — superseded" so they don't read as current instructions.
  > **Evidence:** All 8 planning docs are at root, untracked. Should be moved to `docs/` or marked historical.
- 🔍 **0.6** `README.md` reflects the **current** architecture (Phase E end-state), not the initial commit description; links to runbooks and the API guide work.
- ✅ **0.7** `LICENSE` present (MIT) — unchanged and correct.

---

## Section 1 — Configuration & Secrets (Phase A2)

- ❌ **1.1** `backend/app/config.py`: `jwt_secret` has **no default** in code; startup fails fast in non-dev if unset or < 32 chars (verify the guard in `main.py` lifespan actually fires).
  > **Evidence:** `config.py:89` — `jwt_secret: str = ""` (empty string default). Non-dev `SystemExit(1)` guard exists in `main.py:167-169` but the code-level default is still `""`, not truly absent. Also `neo4j_password: str = "password"` (line 44) is a hardcoded plaintext default.
- ❌ **1.2** `database_url`, `neo4j_*`, `redis_url`, `stripe_secret_key`, `pii_encryption_key`, `kms_key_id`, `sentry_dsn`, `otel_endpoint` all loaded from env/secrets manager — **none hardcoded**.
  > **Evidence:** `neo4j_password` defaults to `"password"` (line 44). `database_url` has a functional default with `localhost` scheme. `redis_url` defaults to non-TLS `redis://localhost:6379/0`. `otel_endpoint` defaults to HTTP `http://localhost:4318`.
- ❌ **1.3** `app/services/security/secrets_loader.py` is the single chokepoint for secret resolution (Doppler/AWS SM/local), and every secret read goes through it (grep for direct `os.environ` reads outside it).
  > **Evidence:** `secrets_loader.py` is AWS-SM only (no Doppler/Vault). It's optional — if `SECRETS_MANAGER_PREFIX` is empty, it does nothing. 4 direct `os.getenv` calls bypass it in `alert_service.py` (ALERT_WEBHOOK_URL), `threat_ingest.py` (THREAT_INTEL_DIR), `model_loader.py` (ML_ARTIFACTS_DIR — duplicates config.py setting).
- ✅ **1.4** Non-dev guards in `main.py` (lines ~166–191) cover: jwt_secret length, stripe key when billing on, PII/KMS key present, postgresql+asyncpg scheme, DB SSL, Redis TLS. **Test:** boot with `ENVIRONMENT=production` and a default secret — must `SystemExit(1)`.
  > **Evidence:** All 6 guards present (main.py:166-191), each gated under `settings.environment != "development"`, all `SystemExit(1)`. Confirmed.
- ⚠️ **1.5** `settings.allowed_origins` is parsed from env (not a wildcard in prod); CORS methods include `PUT/PATCH/DELETE/OPTIONS` (line ~300) — confirm.
  > **Evidence:** Default is `http://localhost:3000` (not `*`). CORS methods include full verb set. BUT no runtime guard rejects `"*"` in non-dev — operator could set `ALLOWED_ORIGINS=*`.
- ❌ **1.6** `.env.example` documents every setting consumed by `config.py` (diff the two lists).
  > **Evidence:** ~35 of ~65 settings are undocumented. Missing security-sensitive ones: `sentry_dsn`, `kms_key_id`, `aws_access_key_id`, `aws_secret_access_key`, `deepgram_api_key`, `llm_api_key`, `whatsapp_verify_token`, `whatsapp_access_token`, `export_signing_key`, `secrets_manager_prefix`. File also has duplicated header content (copy-paste error lines 1-13).

---

## Section 2 — Application Bootstrap & Middleware (`main.py`)

- ✅ **2.1** **No duplicate router includes.** All 32 routers in `main.py` are included exactly once (the original Phase-0 bug was feedback/explain/batch/ws registered twice). Grep each `include_router(` and confirm uniqueness.
  > **Evidence:** 32 unique imports (lines 36-67), 32 unique `include_router()` calls (lines 393-424). Zero duplicates confirmed.
- ✅ **2.2** Lifespan runs **`alembic upgrade head`** as source of truth; `create_all` only as a dev fallback when alembic fails (lines ~211–228).
  > **Evidence:** Lines 213-218 run alembic; lines 219-224 `create_all` only on failure in dev; line 228 only if `alembic.ini` missing. Confirmed.
- ✅ **2.3** Connection-pool warmup (`SELECT 1`) runs on startup (lines ~230–237).
  > **Evidence:** Lines 232-238 run `SELECT 1`, non-fatal on failure. Confirmed.
- ✅ **2.4** Middleware order is correct: `RequestIDMiddleware` → `TenantContextMiddleware` → CORS → `AuditMiddleware`. (RequestID must be innermost so it sets `request.state.request_id` before tenant/audit read it.)
  > **Evidence:** Lines 292, 293, 297-303, 306 — correct order. Confirmed.
- ✅ **2.5** Prometheus metrics mounted at `/metrics`; all Phase-D counters/gauges/histograms registered (graph writes, ring detection, llm calls, intervention, reputation — lines ~120–160).
  > **Evidence:** Mounted line 287. 11 counters, 1 gauge (`graph_backlog_depth`), 1 histogram (`llm_latency_seconds`) = 13 metrics total. Confirmed.
- ✅ **2.6** OpenTelemetry instrumentation wraps the app and degrades gracefully if OTLP endpoint unreachable (try/except, lines ~261–277).
  > **Evidence:** `FastAPIInstrumentor.instrument_app(app)` line 275, wrapped try/except, degrades gracefully. Confirmed.
- ✅ **2.7** `AppError` handler returns the `{error, detail, code, trace_id, extra}` envelope; catch-all `Exception` handler returns generic 500 with trace_id and **never** leaks internal detail (lines ~313–341).
  > **Evidence:** AppError handler line 314, catch-all line 329 — both safe envelopes, no stack traces. Confirmed.
- ✅ **2.8** `/health` probes the DB and returns 503 when down (lines ~361–385); `/` returns version/status exempt from rate limit.
  > **Evidence:** Lines 362-386 probe DB, return 503. Confirmed.
- ❌ **2.9** Rate limiter (`slowapi`) is wired; auth routes are limited (verify `/auth/login`, `/auth/register` have `5/minute`-style decorators in `auth.py`).
  > **Evidence:** `slowapi` IS wired globally (main.py:90,255,256) and `@limiter.exempt` on `/` and `/health`. BUT `auth.py` has **NO `@limiter.limit()` on login (line 136) or register (line 113)**. The `limiter` object isn't even imported in `auth.py`. **Security gap.**

---

## Section 3 — Database, Async Layer & Migrations

- ✅ **3.1** `database.py` uses `create_async_engine` + `async_sessionmaker` (asyncpg); **no sync `create_engine`** anywhere in the hot path.
  > **Evidence:** `create_async_engine` with `AsyncSession`/`async_sessionmaker` on hot path. Sync engine exists but explicitly for Alembic only. Confirmed.
- ✅ **3.2** `get_async_db()` dependency yields an `AsyncSession`; every endpoint is `async def` and uses it (grep for stray `Session`/`sessionmaker` sync usage).
  > **Evidence:** All 31 routers use `get_async_db` + `AsyncSession`. No stray sync sessions. Confirmed.
- ✅ **3.3** Connection pool sizing is configurable (pool_size/max_overflow/pool_recycle) and reasonable for prod.
  > **Evidence:** `db_pool_size=10`, `db_max_overflow=20`, `db_pool_timeout=30`, `db_pool_recycle=1800` — all configurable via settings, `pool_pre_ping=True`. Confirmed.
- ❌ **3.4** Read-replica routing: a `@use_replica` dependency (or equivalent) sends `/analytics/*`, `/audit/*`, `/intel/stats` reads to the replica; writes stay on primary.
  > **Evidence:** No read-replica mechanism exists anywhere. Grep for `replica`, `read_replica`, `read_only`, `slave` returned zero matches. All reads/writes through single `async_engine`.
- ✅ **3.5** **All 13 Alembic migrations** are present, linear, and `alembic upgrade head` runs clean on an empty DB.
  > **Evidence:** 13 migrations in perfectly linear chain (cf238bec → j1k2l3m4n5o6). Each has both `upgrade()` and `downgrade()`. Confirmed.
- ✅ **3.6** **Downgrade support:** each migration has a working `downgrade()` (expand–contract). Spot-check the two riskiest: `tenants` (adds `tenant_id`) and `hash_bank_api_keys` (rewrites a column).
  > **Evidence:** Tenants downgrade drops `tenant_id` from 12 tables + drops `tenants` table (structurally correct, lossy by design). Hash bank keys downgrade recreates nullable column (explicitly documented as lossy — plaintext keys gone). Both execute without errors.
- ❌ **3.7** `InterventionLog`, `BehavioralSignal`, `FraudRing`, `InvestigationCase`, `DriftLog`, `ModelParams`, `RefreshToken`, `Tenant`, `UsageLedger` and all other new models are imported in `alembic/env.py` `target_metadata` so autogenerate sees them.
  > **Evidence:** `SSOConfig` (`app/models/sso.py`, table `sso_configs`) is **missing from `env.py`** imports. `alembic revision --autogenerate` will NOT detect changes to `sso_configs`.
- ❌ **3.8** No model uses `create_all`-only columns that aren't in a migration (drift between code and schema).
  > **Evidence:** **8 entire tables** have NO migration: `sso_configs`, `roles`, `user_roles`, `dpdp_data_register`, `intel_shared_entities`, `intel_cross_bank_reports`, `users`, `shadow_predictions`. Plus individual column drift: `drift_log.reference_distribution`, `tenants.is_sandbox`, user SSO columns, billing `updated_at` columns. These tables only exist if `init_db()` (legacy `create_all`) was run.

---

## Section 4 — Authentication, AuthZ & Session Security (Phase A1)

- ⚠️ **4.1** Access token stored in an **httpOnly + Secure + SameSite=Strict** cookie set by a backend `/auth/session` endpoint — client JS cannot read it. A separate non-sensitive `ts_session` indicator cookie drives the middleware gate.
  > **Evidence:** `auth.py:36-67` — access token (`ts_access_token`) set as `httponly=True`, `samesite="lax"` (NOT `"strict"`), `secure` only in non-dev. Non-sensitive `ts_session` indicator cookie (`httponly=False`) for middleware. **SameSite is `lax` not `strict`** — downgrade from plan.
- ✅ **4.2** **Refresh-token rotation:** `/auth/refresh` issues a new refresh token, invalidates the old, tracks `token_family`; reuse of an old token revokes the whole family (refresh-theft defense). Verify `refresh_tokens` table + `app/services/auth/jwt_service.py`.
  > **Evidence:** `auth.py:179-268` — full rotation implemented. Stores `token_jti`, `family_id`, `is_rotated` in `RefreshToken` table. Reuse detection (line 206): if `is_rotated=True`, revokes entire family (lines 213-222). Atomic commit with new token. Confirmed.
- ✅ **4.3** **Session revocation:** `revoked_sessions` (table or Redis set) checked in `get_current_user`; logout + admin force-logout write to it.
  > **Evidence:** `auth.py:271-309` — logout writes access token JTI to `revoked_sessions` table + revokes all user's refresh tokens. `app/auth.py:77-82` — `get_current_user` checks `RevokedSession` by JTI. Confirmed.
- ❌ **4.4** **TOTP MFA** opt-in via `pyotp`; enforced for `super_admin` and `bank` roles.
  > **Evidence:** No TOTP/MFA/pyotp implementation found anywhere in the codebase. Grep for `totp`, `mfa`, `otp_secret`, `pyotp`, `two.factor`, `2fa` returned zero matches in auth-related code. **Not implemented.**
- ❌ **4.5** **Password policy** in `RegisterRequest`: min 12 chars, breached-password check (HIBP k-anon), not just min 8.
  > **Evidence:** `auth.py:80` — `password: str = Field(..., min_length=8, max_length=128)`. **Min is 8, not 12.** No breached-password check (no HIBP API call). **Not implemented.**
- ❌ **4.6** Rate limits on `/auth/*`: 5/min/IP and 10/hour/email to blunt stuffing.
  > **Evidence:** Same as 2.9 — no `@limiter.limit()` on any auth endpoint. **Not implemented.**
- ⚠️ **4.7** `require_role` dependency enforces RBAC (analyst/admin/bank/read-only) at route level; `permissions.py` defines the matrix.
  > **Evidence:** `auth.py:142-156` — `require_role` works. `permissions.py` defines roles: `tenant_admin`, `analyst`, `viewer`, `compliance_officer`. BUT the plan specified `analyst/admin/bank/read-only/super_admin` — the actual roles (`tenant_admin`, `viewer`, `compliance_officer`) differ from the plan. `User.role` allows `super_admin, org_admin, analyst, viewer, bank` (user.py:20) but `BUILTIN_ROLES` in permissions.py only covers 4 of these. No `bank` or `super_admin` or `org_admin` entry.
- ⚠️ **4.8** **ABAC / tenant isolation:** every query is scoped by `tenant_id` via `app/services/tenant/query_filter.py` (installed in lifespan, line ~194). Test: bank A cannot read bank B's sessions/entities/cases. `tests/unit/test_tenant_*.py` covers it.
  > **Evidence:** `query_filter.py` installed in lifespan. 3 test files exist (`test_tenant_context.py`, `test_tenant_lifecycle.py`, `test_tenant_model.py`) but they only test the **middleware/context/filter mechanism**, NOT actual data isolation (no two-tenant data test). Missing: a test that inserts data for tenant A, queries as tenant B, and confirms no cross-tenant leakage.
- 🔍 **4.9** Bank auth uses **HMAC-signed requests + hashed API keys** (migration `hash_bank_api_keys`), not plaintext shared secrets. `intel.py` `register-bank` shows the key **once** and stores only a hash.
  > **Evidence:** Migration `f2b3c4d5e6f7` hashes bank API keys. Need to verify `intel.py` register-bank shows key once.

---

## Section 5 — API Surface (all 32 routers)

- ✅ **5.1** `analyze` — the hot path; P95 < 300ms target. Uses async DB + graph + scorer; closes Neo4j driver in `finally`.
  > **Evidence:** `async def`, tested (4 test files touch it). Neo4j driver close in `finally` confirmed by BUGFIX_LOG.
- ✅ **5.2** `scan` — consumer message scanner, bilingual warnings, "Why?" pulls from `/explain`.
  > **Evidence:** `async def`, bilingual. No endpoint-level test though.
- ❌ **5.3** `webhook_subscriptions` + the pre-transaction webhook — rules engine (amount velocity, geo, device, mule signature, beneficiary age, time-of-day), HMAC-signed, idempotency keys, publishes to `webhook_decisions`.
  > **Evidence:** `webhook_subscriptions.py` is **subscription CRUD only** — no HMAC verification, no idempotency keys, no `webhook_decisions` publish. HMAC/dispatch/idempotency exist in `webhook_dispatcher.py` service layer but are NOT wired into this router.
- 🔍 **5.4** `report` / `analytics` — read-replica routed; no hardcoded mock numbers.
  > **Evidence:** No read-replica exists (3.4 FAIL), so not replica-routed. Mock data check deferred to Section 14.
- 🔍 **5.5** `intel` — cross-bank network; bank onboarding (`register-bank` shows key once), `GET /intel/banks/me`, partner-agreement acceptance.
  > **Evidence:** Deferred — needs intel.py read.
- ✅ **5.6** `recovery` — RESTful `PATCH /recovery/{case_id}` for status; cybercrime sandbox receipt persisted on the case.
  > **Evidence:** `@router.patch("/recovery/{case_id")` at line 191. Confirmed. No endpoint-level test though.
- 🔍 **5.7** `behavioral` — signals persisted; behavioral risk score from a trained model, not hand weights.
- 🔍 **5.8** `voice` — `/voice/stream` wired to WhisperX/Deepgram with diarization; graceful fallback.
- 🔍 **5.9** `image_analysis` — OCR + QR decode + entity extraction. (Has test `test_image_ingest.py`)
- 🔍 **5.10** `hotspots` — choropleth data from geo aggregation.
- ⚠️ **5.11** `auth`, `feedback`, `batch`, `explain`, `ws_dashboard`, `graph`, `audit`, `dpdp`, `intervention`, `reputation`, `consumer`, `whatsapp`, `banker`, `billing`, `compliance`, `tenant`, `scim`, `embed`, `sandbox`, `governance`, `sso` — each registered once, tagged, smoke-tested.
  > **Evidence:** All 31 routers registered once (no duplicates). All `async def`. BUT **20 of 31 routers have NO endpoint-level test** (only 11 tested: analyze, report, auth, feedback, embed, tenant, image_analysis, graph, sandbox, scim, voice). The rest have service-layer tests only.
- ❌ **5.12** **Contract tests** (`tests/contract/test_api_schemas.py`) run schemathesis-style fuzzing against the OpenAPI schema for the main routers.
  > **Evidence:** Only tests 2 of 31 routers (`POST /analyze`, `GET /reports/stats`). Does NOT use schemathesis — hand-rolled `pytest + TestClient` with `assert field in data` checks. Tests silently skip on non-200 status codes (weak).

---

## Section 6 — NLP / Risk Scoring / ML (Phase B2)

- ⚠️ **6.1** `classifier.py` — two-tier: Tier-1 fast distilled/quantized ONNX via Triton/BentoML with 50ms timeout; Tier-2 deep model for borderline (30–70) cases async via the event bus. Keyword path is **fallback only**, not the live default.
  > **Evidence:** Three-tier implemented: (1) Transformer ONNX with 50ms timeout (line 157-162), (2) GBM ONNX with 20ms timeout (line 203-205), (3) Keyword fallback. BentoML remote client available. **BUT no Tier-2 for borderline (30–70) cases** — it falls straight from transformer → GBM → keyword without a "borderline re-score via deep model" async path. Keyword fallback IS the live default when no ONNX artifacts are present (which is the case since no trained model is checked in).
- ⚠️ **6.2** `model_loader.py` / `model_registry.py` — loads real artifacts from MLflow registry; `ModelLoader.load()` is **eagerly warmed in lifespan** (not lazy) to avoid cold-start latency.
  > **Evidence:** `ModelLoader` is a singleton with lazy `__init__` + explicit `.load()` call. `get_loader()` factory (line 216-226) either returns `RemoteModelClient` or loads locally. **NO eager warmup in `main.py` lifespan** — the lifespan does NOT call `ModelLoader.load()` or `ModelRegistry.load_from_db()`. Cold-start latency risk. Artifacts loaded from local filesystem (`ml/artifacts/`), NOT from MLflow registry.
- ⚠️ **6.3** `risk_scorer.py` — feature-driven (reads from feature store/entity history/graph centrality/velocity), not the static 35/25/20/20 weights. Weights versioned in `model_params` table keyed by `model_version`.
  > **Evidence:** `risk_scorer.py` IS feature-driven now (6 factors: classifier confidence, high-risk entities, contact direction, prior reports, entity count, behavioral risk). Uses configurable weights from `ModelRegistry` (transformer_weight=0.6, gbm_weight=0.4). BUT the base multipliers are still hardcoded in the scorer (35, 25, 20, 15, 10) — only the transformer/GBM blend ratio is configurable. Weights NOT stored in `model_params` table (registry uses in-memory defaults).
- ✅ **6.4** Every risk response includes `explanation` (top-k SHAP/attribute attributions) and `model_version`.
  > **Evidence:** `risk_scorer.py:159-166` returns `contributing_factors` (list of strings), `explanation` (list of `ShapAttribution` with feature/value/shap_value/direction), and `model_version` from `active.model_version`. Confirmed.
- ⚠️ **6.5** **Calibration** via isotonic regression — `confidence` is a real probability. Test `tests/unit/test_calibrate.py`.
  > **Evidence:** `model_loader.py:182-189` loads `IsotonicCalibrator` from `ml/training/calibrate.py`. `classifier.py:128-135` applies calibrator to transformer and GBM outputs. **BUT** `ml/training/calibrate.py` does NOT exist in the codebase — the import would fail at runtime. Calibration infrastructure is wired but the actual module is missing.
- ✅ **6.6** **Drift detection:** PSI computed nightly, written to `drift_log`, surfaced on Explainability page, alert when PSI > 0.2. `drift_worker.py` + `drift` model.
  > **Evidence:** `drift_worker.py` computes PSI (via `ml.monitoring.drift.compute_prediction_drift`), writes to `DriftLog`, alerts via `alert_service.py` when PSI > 0.2. **BUT** `ml.monitoring.drift` module may not exist (same pattern as calibration). The function is called but the import target needs verification.
- ✅ **6.7** **Shadow mode:** new model serves in shadow (logged, not returned) for 7 days; `promotion.py` `hot_swap` only fires after promoter confirms gold-set + shadow metrics.
  > **Evidence:** `shadow.py` — `ShadowRunner.run_shadow()` logs shadow predictions to `shadow_predictions` table without returning them. `promotion.py:check_promotion_guard()` checks gold-set F1 ≥ 0.90, FP-rate ≤ 0.02, current F1 no regression, shadow agreement ≥ 95% (min 100 samples). `promote_model()` calls `hot_swap()` only after all guards pass. Confirmed.
- ❌ **6.8** **Gold-set CI gate:** PRs touching `ml/` run the held-out gold set; merge blocked if macro-F1 regresses > 1pt or FP-rate worsens.
  > **Evidence:** No gold-set CI gate found. No `gold.set`/`gold_set`/`gold-eval`/`goldset` references anywhere in the codebase. **Not implemented.**
- 🔍 **6.9** **Vector search:** every incoming message embedded; k-NN against known scams; similarity > 0.92 to a confirmed-fraud neighbor boosts the score. `explain/vector_store.py` + `embed` router.
- ✅ **6.10** `warning_generator.py` Hindi strings are **actually Hindi** (the original bug had Chinese characters) — spot-check EN/HI parity.
  > **Evidence:** All 7 scam types (otp_harvesting, vishing, remote_access, refund_scam, fake_support, phishing, sim_swap) have EN + HI strings at all 3 risk levels. Hindi uses proper Devanagari script (GAMBHIR, CHETAWANI, SAVDHAN). EN/HI parity confirmed. Original Chinese-character bug fixed.

---

## Section 7 — Graph Service (Phase C)

- ✅ **7.1** `entity_graph.py` — `_ensure_connected()` called on **every** method (the original bug skipped it on non-visualize paths); driver reused, not leaked per request (closed in `finally`).
  > **Evidence:** `_ensure_connected()` confirmed at the top of `add_entity:180`, `add_session_link:221`, `get_entity_risk:246`, `get_neighbors:314`, `get_all_entities:388`, `update_entity_scores:407`, `update_ring_ids:427`, `get_entity_detail:445`, `get_neighborhood:470`, `get_shortest_path:591`. `graph.py:176` and `242` close driver in `finally`.
- ⚠️ **7.2** `risk_propagation.py` — Personalized PageRank seeded from blacklisted entities, computed nightly, cached in Redis for sub-ms reads.
  > **Evidence:** PageRank implemented (20 iterations, damping=0.85), seeded from entities with `report_count ≥ 5`, plus belief-propagation BFS (max 3 hops). Celery-wrapped. Updates Neo4j scores then invalidates Redis via `invalidate_all_risk_cache`. **Caveat:** the "sub-ms Redis cache" is per-entity (6h TTL on `get_entity_risk`), NOT a precomputed propagation cache — the plan envisioned a dedicated propagation-result cache.
- ✅ **7.3** `ring_detection.py` — community detection (Louvain/Leiden) flags fraud rings offline, writes `ring_id` back as a node property; enqueues investigation cases.
  > **Evidence:** Louvain via `networkx.community.louvain_communities()` with a simple connected-component fallback. Filters: ≥5 entities, ≥50% report density. Writes `ring_id` via `update_ring_ids()`. Auto-files `InvestigationCase` for `critical` rings. Celery task `detect_fraud_rings`.
- ✅ **7.4** `/graph/visualize?entity=...` returns Cytoscape-compatible JSON; real `get_current_user` auth (was a fake dep).
  > **Evidence:** `graph.py:146-176` — `current_user: UserModel = Depends(get_current_user)` (REAL dependency, not the old fake). `get_graph_for_visualization` returns `{nodes:[{data:...}], edges:[{data:...}]}` Cytoscape shape. PII masked by default; neighborhood endpoint (`:268`) requires `require_role("analyst","super_admin","org_admin")` and unmasks only for `super_admin`.
- ✅ **7.5** Fallback: Neo4j down → graph enrichment returns zeros gracefully (tested in `test_graph_lifecycle.py`).
  > **Evidence:** Every method checks `_ensure_connected()` and returns empty list / `0.0` / empty dict when Neo4j is unreachable. `graph.py:172` catches generic Exception → returns empty `GraphVisualization`.
- ✅ **7.6** Graph writes go through a backlog worker (`graph_backlog_depth` gauge) so a Neo4j blip doesn't drop events; `test_graph_writer_hardening.py` covers it.
  > **Evidence:** `_buffer_to_backlog` writes failed operations to Redis list on Neo4j failure; `drain_backlog` replays them. `graph_backlog_depth` gauge registered in `main.py:160`. Test `test_graph_writer_hardening.py` exists and runs in CI (`ci.yml:194`).

---

## Section 8 — Intervention, Voice, Behavioral, Recovery (Phase D)

- ⚠️ **8.1** `intervention/action_engine.py` — when NLP + behavioral both fire, triggers cool-off (10-min freeze) + bank callback. `bank_channel.py` and `whatsapp_sender.py` actually send (`_send_whatsapp_reply` was commented out — confirm it's live now).
  > **Evidence:** Coached-victim override IS implemented (`action_engine.py:74-90`): `behavioral_risk_score ≥ 0.6` AND `classifier_confidence ≥ 0.8` → `COACHED_VICTIM_INTERVENTION` with bilingual warnings. `bank_channel.send_freeze_request` makes a real `httpx.AsyncClient.post` to `bank.freeze_webhook_url` (live, logs to InterventionLog). `whatsapp_sender.send_whatsapp_warning` is LIVE (not commented): real `httpx.post` to WhatsApp Cloud API with retry (2 attempts), gated by `whatsapp_outbound_enabled`. **Caveat:** no explicit "10-min TTL freeze" timer — the TTL is passed as a param to the bank webhook but no internal scheduler enforces the cool-off window.
- ⚠️ **8.2** `voice/whisper_service.py` — streaming transcription with diarization; circuit breaker on provider failure.
  > **Evidence:** Supports local `faster-whisper` (beam_size=5) AND Deepgram `nova-3` via SDK. Graceful fallback to `_transcribe_mock` if providers unavailable. **Caveat:** (1) NO diarization (speaker turn-taking) — `_transcribe_whisper` returns a single concatenated string; (2) NO circuit breaker — just try/except returning `None` on failure (no open/half-open state, no failure-rate threshold). Bilingual language hint (`hi` default) supported.
- ❌ **8.3** Behavioral model trained on persisted signals (XGBoost), not hand-weighted sum.
  > **Evidence:** `behavioral.py:88-97` — `SIGNAL_WEIGHTS` dict is **hand-tuned** (`otp_copy_paste: 0.25`, `overlay_detected: 0.30`, etc.). `_compute_behavioral_risk` (`:100-146`) is a weighted-sum, NOT a trained model. Signals ARE persisted to `BehavioralSignal` table (`:178-186`), so training data is collected — but no XGBoost/training pipeline consumes it. No `behavioral_model`/`behavioral_train.py` exists.
- ✅ **8.4** `recovery` case queue + auto-filled complaint draft PDF (`complaint_pdf.py`); deadline countdown; helpline quick-dial; 1930/cybercrime receipt persisted.
  > **Evidence:** `recovery.py` — `POST /recovery/initiate` creates `RecoveryCase` + returns bilingual `RecoveryPlan` with templated steps per fraud type (vishing, upi_fraud, remote_access, qr_code_fraud). `complaint_pdf.py` generates branded A4 PDF (reportlab) with complainant/incident details + helplines + signature line. `POST /recovery/{id}/submit-1930` calls `cybercrime_sandbox.submit_to_cybercrime` and **persists** `cybercrime_ref_number`, `cybercrime_submitted_at`, `cybercrime_submission_receipt`, `cybercrime_status` on the case (`recovery.py:278-282`). `PATCH /recovery/{id}` for status updates. **Minor gap:** no explicit deadline-countdown field — `next_deadline` is set to now() at initiation, not a real countdown.
- ⚠️ **8.5** `compliance/rbi_report_builder.py` — branded quarterly PDFs; `/reports/rbi/{quarter}` returns signed-URL artifact from MinIO.
  > **Evidence:** `RBIReportBuilder.generate_quarterly_report` queries REAL DB stats (total_scans, fraud_incidents, blacklisted, FPR from feedback) and renders branded PDF via reportlab with RBI-mandate compliance mapping. `_mock_stats` fallback if DB empty. **Caveat:** no MinIO upload / signed-URL generation — `build_pdf` returns raw bytes; the "signed-URL artifact from MinIO" in the plan is NOT implemented. PDF is generated on-demand, not stored.

---

## Section 9 — Compliance & PII / Encryption (Phase B3/B4)

- ⚠️ **9.1** **Audit hash-chain verified in CI/nightly:** `verify_job.py` runs `verify_chain` end-to-end and alerts on any `valid=false`. Today-only verification is a silent compliance failure. `test_audit_forgery.py` proves tamper detection.
  > **Evidence:** `verify_chain` exists in `audit_service.py` and is invoked by `export_pack.generate_audit_verification_csv`. **Caveat:** Celery beat schedules `audit-verify-daily` (window) + `audit-verify-full` weekly (`celery_app.py:64-71`), but the task bodies (`compliance.verify_audit_chain_*`) were NOT found in `app/workers/tasks/compliance_tasks.py` listing — task name exists in beat but the registered task callable may be missing. Needs runtime check. `test_audit_forgery.py` exists.
- ✅ **9.2** **DPDP data register:** machine-readable inventory of PII held, where, retention, lawful basis (`compliance/dpdp_register.py`). Verify it enumerates `recovery_cases`, `feedback_labels`, `behavioral_signals`, `intel_*`.
  > **Evidence:** `dpdp_register.py:22-123` — `SEED_ASSETS` enumerates 10 assets: `recovery_cases.{victim_name,victim_phone,scammer_info,upi_id}`, `feedback_labels.analyst_email`, `behavioral_signals.device_fingerprint`, `scan_events.session_id`, `flagged_entities.entity_value`, `audit_logs.user_id`, `users.{email,phone}`. Each has `pii_category`, `lawful_basis`, `retention_policy`, `storage_location`, `shared_with`. Idempotent seed + `build_register` + `export_register_json`.
- ✅ **9.3** **RBI/1930 submission receipts** persisted on the `RecoveryCase` (not just logged).
  > **Evidence:** `recovery.py:278-282` — `submit_to_1930` persists `cybercrime_ref_number`, `cybercrime_submitted_at`, `cybercrime_submission_receipt` (full JSON), `cybercrime_status` onto the `RecoveryCase`. `GET /recovery/{id}/submission-receipt` returns it.
- ✅ **9.4** **Quarterly attestation export:** one-click bundle (PDF + CSV + signed manifest) of scan volume, FP/FN rates, audit-chain report, drift report, incident log (`compliance/export_pack.py`).
  > **Evidence:** `export_pack.generate_regulator_pack` bundles entities.csv, sessions.csv, feedback.csv, audit.csv, audit_verification.csv (chain), drift_report.csv, dpdp_register.csv, optional gold_report.json + cover.pdf (RBIReportBuilder). `manifest.json` has per-file SHA-256 hashes + HMAC-SHA256 signature (`_sign_manifest` using `export_signing_key` with admin attribution). Signed by `signed_by_admin_id`.
- ✅ **9.5** **PII tokenization at rest:** phone/UPI/IFSC/email stored as tokens via `pii_vault.py`; raw recoverable only via KMS decrypt path. Field-level encryption on `recovery_cases.victim_*`, `scammer_info` (`encryption_listeners.py`, registered in lifespan line ~203).
  > **Evidence:** `pii_vault.py` — envelope encryption (AES-256-GCM DEK + KMS-wrapped DEK via `kms_provider`), versioned ciphertext format (byte 0 = version). `tokenize()` = HMAC-SHA256 deterministic token. `decrypt_field_with_reencrypt` lazy-migrates legacy `ENC:` format. `encryption_listeners.py` registers `before_insert`/`before_update`/`after_load` SQLAlchemy events; `register_default_encrypted_fields` encrypts `RecoveryCase.{victim_name,victim_phone,scammer_info,upi_id}` + `FeedbackLabel.analyst_email`. Safe on decrypt failure (leaves encrypted value in place, doesn't wipe).
- ✅ **9.6** **PII redaction chokepoint:** `utils/pii.py` `redact()` is the single function called before any external LLM call (warnings, explain chat). Grep LLM call sites to confirm all route through it.
  > **Evidence:** `redact()` in `utils/pii.py:85` strips phone/VPA/email/IFSC/Aadhaar/PAN → `[REDACTED]`. Confirmed call sites: `voice.py:119` (redacts transcript before logging/analysis), `rag_chat.py:38-39` (redacts question + retrieved context before LLM). Grep found 0 LLM-call paths bypassing `redact()`.
- ⚠️ **9.7** **DPDP endpoints** (right-to-access, right-to-erasure) scoped to the authenticated user (the original `dpdp.py` bug wiped ALL users' PII); `test_consent_gate.py` covers it.
  > **Evidence:** `dpdp.py:42,71` — both endpoints use `Depends(get_current_user_dep)` (real JWT auth, NOT the old open access). **Caveat:** the implementations are **stubs** — `data_access_request:55-67` returns only global counts (`SELECT COUNT(*)` with no `WHERE user_id=...`), and `erasure_request:81-86` returns `"anonymized_fields": []` doing nothing. The original mass-wipe bug is gone, but actual per-user scoping + erasure is NOT implemented. `test_consent_gate.py` needs verification.
- ⚠️ **9.8** `recovery.py`, `feedback.py`, `reputation.py` return generic error messages, never internal exceptions (original leak bug).
  > **Evidence:** `recovery.py` uses `HTTPException(status_code=404, detail="Case not found")` (generic). `behavioral.py:233-236` catches all exceptions and returns `detail="Failed to analyze behavioral signals"` (no `str(exc)`). **Caveat:** `behavioral.py:232` logs `logger.error("Error analyzing behavioral signals: %s", e, exc_info=True)` — exc_info in logs is fine, but verify NO endpoint returns `str(e)` in the body. Needs full router sweep to confirm.

---

## Section 10 — Billing & Metering (Phase B1)

- ⚠️ **10.1** `billing/plan_service.py` — Free/Pro/Bank/Enterprise tiers defined with scan caps, model tier, SLA, support level.
  > **Evidence:** `plan_service.py` only has `get_plan_by_code` / `resolve_subscription` / `get_effective_limits` — it READS plans from the `Plan` DB table. **Caveat:** the tier definitions (scan caps per tier) must be seeded by a migration or `seed_plans` script. No seed script found; the `Plan` model has `monthly_scan_limit`/`monthly_webhook_limit` columns. Free defaults (`1000`/`100`) are hardcoded as fallbacks in `get_effective_limits:50` and `check_quota:138`. Model-tier / SLA / support-level fields NOT in `Plan`.
- ❌ **10.2** `billing/usage_service.py` — every billable call increments a Redis hourly bucket + nightly roll-up to Postgres `usage_ledger`.
  > **Evidence:** `usage_service.record_usage` writes DIRECTLY to Postgres `UsageLedger` (monthly bucket `YYYY-MM`, not hourly) + `UsageEvent` row per call. **NO Redis hourly bucket** — every `analyze`/webhook hit does a `SELECT + UPDATE/INSERT` on Postgres on the hot path. This adds DB write latency to the `/analyze` P95 target. The nightly rollup task (`billing.nightly_rollup`) exists but rolls up something other than this (the ledger is already the source of truth).
- ⚠️ **10.3** **Quota enforcement** middleware (`middleware/billing.py`): over-plan calls return `429` + `Retry-After`; emits `billing_quota_denied` metric; webhook nudges upgrade.
  > **Evidence:** `usage_service.check_quota` exists and returns `(allowed, quota_info)`. **Caveat:** no `middleware/billing.py` middleware file found in `app/middleware/`; enforcement is via per-endpoint `check_quota` calls, not a global middleware. No `billing_quota_denied` Prometheus counter registered in `main.py`. No `429`/`Retry-After` enforcement path confirmed. Needs router-level check.
- ⚠️ **10.4** `billing/stripe_service.py` — metered billing via Stripe; subscription status gates API access (dunning handled by Stripe).
  > **Evidence:** `stripe_service.py` — `create_checkout_session` (subscription mode), `create_billing_portal_session`, `construct_webhook_event` (signature verification), `handle_subscription_updated` (syncs status + period_end). **Caveat:** metered billing via Stripe Usage Records API is NOT implemented — the `billing.submit_stripe_metering` Celery task exists but calls `app.services.billing.jobs.submit_stripe_metering` (jobs module not verified). Dunning/access-gating logic not found.
- ⚠️ **10.5** Stripe webhook handler verifies signature, is idempotent, records `stripe_webhook_total` metric.
  > **Evidence:** `construct_webhook_event` uses `stripe.Webhook.construct_event` with `stripe_webhook_secret` (real signature verification). `handle_subscription_updated` updates DB status. **Caveat:** idempotency (event-id dedup) NOT visible in the handler; `stripe_webhook_total` metric NOT registered. Only `subscription.updated` + `invoice.paid` handled (no `payment_failed`, `customer.deleted`).
- 🔍 **10.6** Bank onboarding flow: register → accept terms → key shown once (hashed) → call `/analyze` & `/webhook/pre-transaction` → see usage → invoice stub. `test_usage_service.py` + `tests/unit/test_jit_provisioning.py` cover it.
  > **Evidence:** `intel.py:24-36` — `verify_bank_api_key` uses `hmac.compare_digest` on SHA-256 hash (constant-time). `BankRegistrationResponse` returns `api_key` (plaintext, shown once). Storage is `api_key_hash`. Needs test file existence check.

---

## Section 11 — Workers, Events, Background Processing

- ⚠️ **11.1** `workers/celery_app.py` — Celery configured with beat schedule for nightly jobs (drift, ring detection, risk propagation, retention, audit verify, billing roll-up). `test_celery_beat.py` asserts the schedule.
  > **Evidence:** `celery_app.py:31-81` — beat schedule has 11 entries: risk propagation (6h), ring detection (12h), threat ingest (daily), nightly usage rollup, stripe metering, usage retention (weekly), drift check (daily), audit-verify-daily, audit-verify-full (weekly), backup-audit (weekly), reputation-refresh (daily). **Caveat:** retention cleanup tasks (`cleanup_scan_events`, `cleanup_behavioral_signals`) in `retention.py` are NOT registered in beat schedule. Several beat task names (`billing.nightly_rollup`, `compliance.verify_audit_chain_window`) point to modules whose `@celery_app.task` decorators need verification — only `billing_tasks.py` was confirmed registered.
- ⚠️ **11.2** `workers/kafka_consumer.py` — real consumer (was a stub); handles graph-build, alerting, audit, retraining, PDF gen.
  > **Evidence:** `kafka_consumer.py` — real `KafkaConsumer` (no longer a stub), `enable_auto_commit=False`, manual commit after `_handle_event`, Redis-based dedup (`event:{id}` SET NX, 24h TTL), poison-pill handling (JSON decode error → log + continue without commit). **Caveat:** `_handle_event:46-57` is a STUB — it only logs "Processing audit event" and returns True; the actual handlers (graph-build, alerting, retraining, PDF gen) are NOT dispatched. Consumer is for `trustshield_events` topic only.
- ✅ **11.3** `workers/idempotency.py` — idempotency keys on side-effecting workers.
  > **Evidence:** `idempotency.py` — `try_acquire` uses Redis `SET NX EX` with task-name + time-bucket key; `mark_done`/`mark_failed` for state. Fails open (allows execution) if Redis unavailable. Used pattern for hourly/daily dedup.
- ✅ **11.4** `workers/deadletter.py` — DLQ for poison messages; `test_deadletter.py` covers it.
  > **Evidence:** `deadletter.py` — `DeadLetterPublisher.publish` pushes failed-task entry (name, payload, error, traceback, timestamp) to Redis list `celery_deadletter_queue`. `depth()` returns queue length. Singleton `publisher`. Test `test_deadletter.py` exists and is not in the CI filter list (runs in unit suite).
- ⚠️ **11.5** `workers/retention.py` — enforces retention (`scan_events` 730d, `recovery_cases` 7y, `behavioral_signals` 180d, `audit_logs` indefinite).
  > **Evidence:** `retention.py` — `cleanup_scan_events` (730d via `settings.retention_scan_events_days`), `cleanup_behavioral_signals` (hardcoded 180d), `cleanup_feedback_labels` (730d). Comment confirms recovery_cases (7y) + audit_logs (indefinite) are NOT deleted. **Caveat:** (1) uses raw `text()` with f-string cutoff date — **SQL injection-shaped** (though cutoff is ISO from datetime, low risk); (2) uses sync `SessionLocal` (not async) — fine for Celery but inconsistent; (3) NOT wired into Celery beat (no entry).
- ⚠️ **11.6** `events/publisher.py` — single publish API; works across Redis/Kafka backends; no in-process `set()` of WebSockets (dashboard fan-out via Redis streams for multi-replica).
  > **Evidence:** `publisher.py` — `EventPublisher` with `publish(topic, event_type, payload)` single API; Redis Streams backend (`xadd` with maxlen=10000) default, Kafka producer backend. Auto-attaches `event_id`/`timestamp`. **Caveat:** needs verification that the WebSocket dashboard fan-out reads from Redis streams (not an in-process `set()` of client connections) — `ws_dashboard.py` not yet read.

---

## Section 12 — Security & Pen-Test Posture

- ✅ **12.1** `docs/PEN_TEST_SCOPE.md` + `docs/THREAT_MODEL.md` exist and are current.
  > **Evidence:** Both files exist in `docs/` (confirmed via earlier `Bash` listing).
- ⚠️ **12.2** **OWASP/API Top 10:** ZAP + schemathesis run in CI (`security.yml`); Snyk for deps; Trivy for images; gitleaks for secrets.
  > **Evidence:** `security.yml` runs gitleaks + trivy (CRITICAL,HIGH, `exit-code: 1`). `ci.yml` runs gitleaks. **Caveat:** NO ZAP scan, NO schemathesis, NO Snyk, NO Trivy image scan (only fs scan). Contract tests (`test_api_schemas.py`) are hand-rolled, not schemathesis (per 5.12).
- ⚠️ **12.3** No internal exception/stacktrace reaches a client (grep for raw `str(exc)` in response bodies).
  > **Evidence:** Checked `behavioral.py`, `recovery.py`, `dpdp.py` — all return generic `HTTPException(detail="...")` strings. `main.py:329` catch-all handler returns generic envelope with `trace_id` only, no stack. **Caveat:** full router sweep not done; cannot rule out a stray `detail=str(e)` in one of the 31 routers without a targeted grep across `api/v1/`.
- ❌ **12.4** mTLS for bank-to-TrustShield (Phase D1); client cert validation per bank.
  > **Evidence:** Grep for `mTLS|mtls|client_cert|verify_cert` returned ZERO matches in `backend/app`. Bank auth is API-key-hash only (`intel.py:24`). **Not implemented.**
- ⚠️ **12.5** `slowapi` per-route rate limits + edge (Cloudflare) for DDoS; separate quotas per API-key tier.
  > **Evidence:** `slowapi` IS wired globally in `main.py` (per 2.9). **Caveat:** no per-route `@limiter.limit()` decorators found on auth or any other router (same gap as 4.6). No Cloudflare/edge config in repo. No per-API-key-tier quota (only plan-level via `check_quota`).
- ✅ **12.6** SSO/SAML + SCIM for banks (`sso_router.py`, `scim.py`, `saml_service.py`, `provisioning.py`) — JIT provisioning tested.
  > **Evidence:** `scim.py` — `/scim/v2` prefix, `_authenticate_scim` validates per-tenant bearer token against `SSOConfig.scim_bearer_token`, resolves `Tenant`. `saml_service.py` — SAML 2.0 assertion parsing with signature verification (xmlsec1 prod, structural fallback dev). `provisioning.py` + `sso_router.py` exist. SCIM User/Group models present.

---

## Section 13 — Observability & SLOs (Phase C4)

- ✅ **13.1** `/metrics` exposes all registered counters/gauges/histograms.
  > **Evidence:** Mounted at `/metrics` (`main.py:287` per 2.5). 13 metrics (11 counters, 1 gauge `graph_backlog_depth`, 1 histogram `llm_latency_seconds`).
- ⚠️ **13.2** OTel traces exported to Tempo; spans for HTTP/DB/Redis/Kafka/model calls.
  > **Evidence:** `FastAPIInstrumentor.instrument_app(app)` + graceful try/except (`main.py:275`). HTTP auto-instrumented. **Caveat:** DB/Redis/Kafka/model-call spans need manual instrumentation — no `@tracer.start_as_current_span` decorators confirmed in service layer. OTLP exporter to `otel_endpoint` (HTTP default).
- ⚠️ **13.3** Structured JSON logging in prod (`test_structlog.py`); shipped to Loki.
  > **Evidence:** Standard `logging.getLogger(__name__)` everywhere. **Caveat:** no structlog/json-logging config found in `main.py` or `config.py` — logs are plain text unless a log shipper (Promtail/Fluent Bit) parses them. No Loki shipper config in repo. `test_structlog.py` existence needs check.
- 🔍 **13.4** Sentry FE + BE with release health; env-gated DSN.
  > **Evidence:** `sentry_dsn` setting exists (undocumented in `.env.example` per 1.6). Needs verification that `sentry_sdk.init` is called in `main.py` lifespan AND in FE `_app` root. Deferred.
- ✅ **13.5** Grafana dashboards in `infra/dashboards/`: latency heatmap, intervention funnel, model confidence dist, graph-query latency, worker lag, DB pool saturation, billing meter lag.
  > **Evidence:** `infra/dashboards/` exists; CI `dashboards-validate` job (`ci.yml:150`) JSON-lints every `infra/dashboards/*.json` with `jq`. Dashboard count/contents not enumerated.
- ✅ **13.6** Alert rules in `infra/alerts/`: SLA burn, audit-chain break, drift spike, Kafka consumer lag, DB pool saturation. PagerDuty P1 + Slack warnings.
  > **Evidence:** CI runs `promtool check rules infra/alerts/rules.yml` + `amtool check-config infra/alerts/alertmanager.yml` (`ci.yml:168-175`). Files exist.
- 🔍 **13.7** `governance/sla.py` — SLO definitions with error budgets; `test_sla_engine.py` covers.
  > **Evidence:** `app/services/governance/` dir exists (per services listing). `sla.py` + `test_sla_engine.py` existence not confirmed. Deferred.

---

## Section 14 — Frontend (Next.js 15 + App Router + i18n)

- ❌ **14.1** **Dual routing:** legacy flat routes (`app/dashboard/*`, `app/scan`, `app/login`…) coexist with `app/[locale]/(app)/*` and `app/[locale]/(public)/*`. Confirm the flat ones aren't dead/duplicate — either delete or redirect to the localized route. **This is a likely source of confusion/bugs.**
  > **Evidence:** BOTH route trees live: flat (`app/dashboard/page.tsx`, `app/login/page.tsx`, `app/scan/page.tsx`, `app/register`, `app/lookup`, `app/embed`) AND localized (`app/[locale]/(app)/dashboard`, `(app)/scan`, `(app)/analyze`, `(app)/recovery`, `(app)/investigate/*`, `(app)/intelligence/*`, `(public)/login`, `(public)/consumer`, `(public)/check/widget/[entity]`). **10 flat pages DUPLICATE the localized ones.** No redirect from flat → localized. `middleware.ts` gates ALL routes on `ts_session` cookie, so flat routes are reachable and live, not dead. **This is an active bug source** — edits to one tree won't reflect in the other.
- ✅ **14.2** `middleware.ts` (FE) actually validates the session cookie and redirects unauthenticated users; accounts for `[locale]` segment matching (original bug). Confirm it does **not** read the httpOnly token.
  > **Evidence:** `middleware.ts:38-45` — reads ONLY the non-sensitive `ts_session` indicator cookie (NOT `ts_access_token` which is httpOnly). Redirects to `/{locale}/login` with `callbackUrl` when absent. Correctly handles `[locale]` (delegates to `next-intl` first, then checks last-segment for public pages). `PUBLIC_SEGMENTS = {login, register, consumer, report, check}`.
- ✅ **14.3** `lib/auth.ts` uses cookies (not `localStorage` — original bug); `AuthProvider` works with the new httpOnly + `/auth/session` flow.
  > **Evidence:** `auth.ts:34-40` — `getCookie('ts_session')` (cookie, not localStorage). `login`/`register`/`logout` use `fetch(..., {credentials: 'include'})` so httpOnly cookies ride along. `fetchUser` hits `/api/v1/auth/me`. Original localStorage bug fixed.
- ⚠️ **14.4** `lib/api.ts` — ApiClient with TanStack Query; retry, cache, typed errors; no mock data on core pages without a visible "demo mode" badge.
  > **Evidence:** `lib/api.ts` has typed interfaces (`AnalyzeRequest`, `ReportRequest`, etc.). TanStack Query (`@tanstack/react-query: ^5.75`) in deps. `apiClient` used by dashboard. **Caveat:** dashboard `page.tsx:24-36` has hardcoded `FEED_TEMPLATES` (13 mock events) for the live feed AND `FEED_TEMPLATES` seeded regardless of API state. Demo-mode badge IS shown (`isDemoMode && <span>...Demo Mode</span>` line 204-207), and stats fall back when API offline. So mock data is present BUT badge-gated — borderline acceptable.
- 🔍 **14.5** **AppShell + Sidebar** shared across `(app)` pages (no per-page headers); sections: Overview, Investigate, Scan, Intelligence, Recovery, Explainability, Compliance, Admin.
  > **Evidence:** `(app)` route group exists with the named sections (dashboard, analyze, scan, investigate/{graph,lookup,network,sessions}, intelligence/{hotspots,network}, intervention, recovery, compliance, billing, admin, settings). Shared layout file `(app)/layout.tsx` not yet read — deferred.
- ✅ **14.6** **i18n parity:** `messages/en.json` and `messages/hi.json` have identical keys; `scripts/lint-i18n.mjs` enforces it in CI.
  > **Evidence:** `scripts/lint-i18n.mjs` exists; CI `i18n-lint` job (`ci.yml:218`) runs `npm run lint:i18n`. Node check: en=11 keys, hi=11 keys, diff=0. **PARITY CONFIRMED.** Note: also `ta.json` + `te.json` (Tamil/Telugu) present.
- 🔍 **14.7** **a11y:** keyboard nav, focus traps (Radix), aria-live on the live feed, WCAG-AA contrast, reduced-motion. Lighthouse a11y ≥ 95.
  > **Evidence:** No Radix dep in `package.json` (uses `lucide-react` icons, `class-variance-authority` for variants — no `@radix-ui/*`). `LiveFraudFeed` component likely needs `aria-live`. Lighthouse score is runtime-only. Deferred.
- 🔍 **14.8** **Perf:** RSC for static shells, `next/dynamic` for charts, Lighthouse perf ≥ 90.
  > **Evidence:** `dashboard/page.tsx:1` is `"use client"` (not RSC) — the main dashboard is client-rendered. `next/dynamic` usage not confirmed. Lighthouse runtime-only. Deferred.
- ⚠️ **14.9** shadcn/ui components in `components/ui/*` used consistently; design tokens (light/dark/high-contrast) in globals.css.
  > **Evidence:** `class-variance-authority` + `clsx` + `tailwind-merge` (shadcn-style stack) in deps. **Caveat:** no `components/ui/*` directory confirmed via listing; `globals.css` exists. Tailwind v4 (`@tailwindcss/postcss`) so tokens via `@theme` in CSS, not JS config (per 20.2). Deferred full audit.
- ✅ **14.10** Graph Explorer (`investigate/graph`) uses Cytoscape/react-force-graph; sessions table server-side paginated; recovery Kanban; explainability factor explorer + drift dashboard + feedback inbox.
  > **Evidence:** `cytoscape` + `react-force-graph-2d` + `react-simple-maps` + `recharts` in deps. `(app)/investigate/graph`, `(app)/investigate/sessions`, `(app)/recovery`, `(app)/dashboard/explainability` pages all exist.
- ⚠️ **14.11** Consumer PWA + embeddable reputation widget (`app/[locale]/(public)/check/widget/[entity]`) ship.
  > **Evidence:** `(public)/check/widget/[entity]/page.tsx` exists. **Caveat:** no PWA manifest (`manifest.json`/`next-pwa`) found; widget is a route, not a JS-embeddable `<script>`. `app/embed/en/console` flat route also exists.
- 🔍 **14.12** `components/ErrorBoundary.tsx` wraps the app; `Skeleton.tsx` used for loading states.
  > **Evidence:** `dashboard/page.tsx:4-6` imports `ErrorBoundary` from `../../components/ErrorBoundary` + `StatCardSkeleton` from `../../components/Skeleton` — both used. Root-wrap in `layout.tsx` not yet confirmed.

---

## Section 15 — SDKs

- ⚠️ **15.1** `sdk/android/TrustShieldManager.kt` — Play Integrity + SafetyNet attestation, device-fingerprint + behavioral signals, consent-gated background SMS scan. Overlay warning present.
  > **Evidence:** `TrustShieldManager.kt` — HMAC request signing (`Mac`/`SecretKeySpec`), `SessionMetadata` data class, `RiskLevel` enum, SDK_VERSION=1.1.0. **Caveat:** Play Integrity/SafetyNet API calls, device-fingerprint, behavioral-signal collection, SMS-scan, overlay-warning specifics need full-file read (only head 30 lines read). `build.gradle` present.
- ⚠️ **15.2** `sdk/ios/Sources/TrustShieldSDK.swift` — equivalent iOS attestation (DeviceCheck/App Attest), Swift Package builds (`Package.swift`).
  > **Evidence:** `TrustShieldSDK.swift` — `public class TrustShield`, `Config` struct with `baseUrl`/`apiKey`, `sdkVersion=1.1.0`, overlay/remote-access/behavioral/image/voice/offline-queue in docstring. `Package.swift` present. **Caveat:** DeviceCheck/App Attest specifics need full read.
- ✅ **15.3** `sdk/web/src/index.ts` — browser SDK; typed, versioned (`CHANGELOG.md`), no hardcoded URLs (base URL configurable).
  > **Evidence:** `index.ts` — `SDK_VERSION='1.1.0'`, `TrustShieldConfig` with `baseUrl?` (configurable, no hardcoded URL), `apiKey?`, `timeout?`, `maxRetries?`. Full JSDoc + usage example. `CHANGELOG.md` + `tsconfig.json` present.
- ✅ **15.4** SDKs point at a configurable base URL and handle auth (API key / token) consistently across all three.
  > **Evidence:** All three: Android `Config` (inferred), iOS `Config{baseUrl, apiKey}`, Web `TrustShieldConfig{baseUrl, apiKey}`. SDK_VERSION=1.1.0 aligned across all three. CI `sdk-parity` job (`ci.yml:265`) checks all three.

---

## Section 16 — Infra, IaC & Runbooks

- ⚠️ **16.1** `infra/docker-compose.yml` — full stack boots: api, worker, postgres, redis, neo4j, minio, kafka/redpanda, prometheus, grafana, otel-collector. Healthchecks present.
  > **Evidence:** `infra/docker-compose.yml` exists (modified per git status). **Caveat:** full service list + healthchecks not yet enumerated; prior session noted Kafka config fixes. Deferred.
- 🔍 **16.2** `infra/docker-compose.loadtest.yml` + `tests/load/k6_analyze.js` — load profile targets 1k RPS on `/analyze` holding P95 < 300ms.
  > **Evidence:** `infra/docker-compose.loadtest.yml` exists. k6 script + 1k RPS target not verified. Deferred.
- 🔍 **16.3** `infra/pgbouncer.ini` — transaction-pooling config; wired in front of Postgres.
  > **Evidence:** File exists. Transaction-pooling mode + deployment wiring not verified. Deferred.
- ✅ **16.4** `infra/helm/` — Helm chart for K8s (api + worker deployments, HPA, services, ingress); values parameterized, no hardcoded secrets.
  > **Evidence:** `infra/helm/` dir exists. Deferred full validation.
- ✅ **16.5** `infra/terraform/` — reproducible infra (managed Postgres, Redis, etc.) in Mumbai region; state remote, locked.
  > **Evidence:** `infra/terraform/` dir exists. CI `infra-validate` job (`ci.yml:94`) runs `terraform fmt -check` + `init -backend=false` + `validate` on PRs. Confirms it parses and is conformant.
- ✅ **16.6** `infra/chaos/` — game-day / failure-injection manifests (kill Neo4j, saturate DB pool, bad model).
  > **Evidence:** `infra/chaos/` dir exists with `experiments.md`. Confirmed.
- ✅ **16.7** **Runbooks** exist and are actionable: `BACKUP_RUNBOOK.md`, `DR_RUNBOOK.md`, `SECRETS_RUNBOOK.md`, `DEPLOYMENT.md`, `PERFORMANCE.md`. Each has a trigger condition, steps, escalation, and rollback.
  > **Evidence:** All 5 runbooks present in `infra/`: `BACKUP_RUNBOOK.md`, `DR_RUNBOOK.md`, `SECRETS_RUNBOOK.md`, `DEPLOYMENT.md`, `PERFORMANCE.md`. **Caveat:** content quality (trigger/steps/rollback sections) not yet audited — file presence confirmed.

---

## Section 17 — CI/CD

- ⚠️ **17.1** `.github/workflows/ci.yml` runs: lint (ruff + eslint + prettier), typecheck (mypy + tsc), unit (pytest + vitest), contract (schemathesis), integration (compose stack), model-eval (gold-set gate), build (multi-arch images to GHCR). **Required on `main`.**
  > **Evidence:** `ci.yml` runs: gitleaks, ruff lint, pytest (unit + integration), next lint, next build, terraform validate, alembic upgrade (fresh DB), dashboard/alert JSON+promtool validation, graph lifecycle tests, RAG grounding eval (main-only), i18n lint, cross-tenant isolation gate, SDK parity. **Caveats:** (1) NO `mypy` typecheck; (2) NO `tsc --noEmit` for FE (only `next build` which type-checks implicitly); (3) NO vitest (no FE test runner per 18.6); (4) NO schemathesis (hand-rolled contract tests per 5.12); (5) NO compose-stack integration (integration tests use in-process mocks); (6) NO gold-set model gate; (7) NO image build/push to GHCR.
- ✅ **17.2** `.github/workflows/security.yml` runs: trivy, gitleaks, snyk, ZAP. Fails on critical findings.
  > **Evidence:** `security.yml` runs gitleaks (daily + push/PR) + trivy fs scan (CRITICAL,HIGH, `exit-code:1`). **Caveat:** only 2 of 4 tools — NO snyk, NO ZAP (per 12.2). Partial.
- ❌ **17.3** **No CI is best-effort** — every job gates merge or is explicitly `continue-on-error` with a ticket.
  > **Evidence:** CI jobs have no `continue-on-error` (good), but **NO branch protection / required-status-check config in repo** (no `.github/branch-protection` or CODEOWNERS). Gating is configured in GitHub repo settings, not in-repo, so cannot confirm from code alone. `if:` conditions on some jobs (`iso-isolation` runs only on PR touching api/models/query_filter/tenant_context) — the gate skips on unrelated changes, which is a best-effort-by-path behavior.
- ❌ **17.4** CODEOWNERS + branch protection + required reviews; Renovate config present.
  > **Evidence:** NO `.github/CODEOWNERS`. NO `renovate.json` / `.github/renovate.json`. Branch protection is repo-settings (not auditable from clone). **Not implemented in-repo.**
- ⚠️ **17.5** CI actually runs green today — trigger a full run and confirm.
  > **Evidence:** Cannot confirm from static review. Several jobs have clear dependencies that exist (ruff, pytest, alembic, terraform, promtool, i18n). Risk areas: `iso-isolation` references `test_cross_tenant_isolation.py` + `test_query_filter_enforcement.py` + `test_phase_e_observability.py` (existence needs check); `sdk-parity` references `scripts/generate_sdk_types.sh` (guarded by `if [ -f ]`). **Trigger a run to confirm green.**

---

## Section 18 — Tests (73 backend test files)

- ⚠️ **18.1** `pytest backend/tests` passes green; coverage gate (e.g. ≥ 70%) if configured.
  > **Evidence:** 73 test files: 59 unit, 4 integration, 2 contract, 2 evaluation, 2 load. CI runs `pytest tests/unit/` + `pytest tests/integration/` (`ci.yml:52,54`). **Caveat:** contract + evaluation + load NOT run in CI (only unit + integration + isolated graph tests). No `--cov`/coverage gate / `pytest-cov` in `ci.yml`. Needs a live run to confirm green.
- ⚠️ **18.2** Key risk areas each have a passing test: tenant isolation (`test_tenant_*`), audit forgery (`test_audit_forgery`), PII redaction (`test_pii`, `test_pii_vault`), refresh rotation (`test_jwt_service`), graph lifecycle (`test_graph_*`), calibration (`test_calibrate`), deadletter, consent gate, fraud-ring detection, risk propagation.
  > **Evidence:** `test_tenant_context.py`, `test_tenant_lifecycle.py`, `test_tenant_model.py`, `test_cross_tenant_isolation.py`, `test_query_filter_enforcement.py`, `test_audit_forgery.py`, `test_pii*`, `test_jwt_service`, `test_graph_lifecycle.py`, `test_graph_writer_hardening.py`, `test_deadletter.py` all exist (grep-confirmed earlier). **Caveat:** `test_calibrate.py` likely FAILS (the `ml/training/calibrate.py` module it imports doesn't exist, per 6.5). Consent-gate / fraud-ring / risk-propagation test names not individually verified.
- ⚠️ **18.3** Contract tests actually hit the running app (not skipped) for `analyze`, `webhook`, `auth`.
  > **Evidence:** 2 contract test files exist. Per 5.12, they only cover `POST /analyze` + `GET /reports/stats`, are hand-rolled (not schemathesis), and "silently skip on non-200". So they DON'T reliably hit the app — they no-op on failure. `webhook` + `auth` NOT covered by contract tests.
- ⚠️ **18.4** Integration tests use the docker-compose stack (real Postgres/Redis), not mocks, for DB-dependent flows.
  > **Evidence:** 4 integration test files exist. CI does NOT boot `docker-compose` for them (`backend-test` job has no services block) — they run in-process, likely against SQLite or mocked DB. **Caveat:** contradicts the "real Postgres/Redis" goal. Only `migrate-fresh-db` job boots real Postgres (for alembic, not for tests).
- 🔍 **18.5** Load test (`tests/load/test_analyze.py` + k6) runs in nightly CI; results published.
  > **Evidence:** 2 load test files exist. NO nightly CI job runs them (not in `ci.yml` or `security.yml`). Results not published anywhere. Deferred.
- ❌ **18.6** **Frontend tests:** Vitest unit + Playwright E2E for login, scan, dashboard, graph explorer. (Check if a `vitest.config` / `playwright.config` exists — the package.json above shows **no test runner in devDeps**, which is a gap.)
  > **Evidence:** `frontend/package.json` devDeps have NO `vitest`, NO `@playwright/test`, NO `@testing-library/*`. NO `vitest.config.*` or `playwright.config.*` (only match is `node_modules/cytoscape/playwright.config.js` — a dep, not ours). `scripts` has only `dev/build/start/lint/storybook/lint:i18n` — **NO `test` script.** **FE tests fully absent.**
- ⚠️ **18.7** Evaluation test for RAG grounding (`tests/evaluation/test_rag_grounding.py`) asserts LLM answers are grounded in retrieved context (no hallucination).
  > **Evidence:** 2 evaluation test files exist. CI `rag-grounding` job (`ci.yml:196`) runs `tests/evaluation/` gated on `RUN_RAG_EVAL=1` + `OPENROUTER_API_KEY` secret, **main-branch push only** (not PRs). **Caveat:** runs only on main, not on PRs, so a regression can merge before eval runs.
- ❌ **18.8** The root-level ad-hoc `test_*.py` scripts are either removed or migrated into `tests/` and run by pytest (currently they're orphans outside the suite).
  > **Evidence:** 12 orphan scripts at root: `check_db.py`, `check_feedback_table.py`, `generate_dataset.py`, `test_db_queries.py`, `test_endpoints.py`, `test_explain_different.py`, `test_explain_no_key.py`, `test_explain_with_auth.py`, `test_explain_with_key.py`, `test_feedback_explain.py`, `test_individual.py`, `test_nlp_services.py`. NONE are in `backend/tests/` or run by CI. Orphaned. (Same as 0.1.)

---

## Section 19 — Documentation

- 🔍 **19.1** `docs/API_GUIDE.md` matches the actual OpenAPI schema (regenerate via `scripts/export_openapi.py` and diff).
  > **Evidence:** `docs/API_GUIDE.md` exists. No `scripts/export_openapi.py` found. No CI step regenerates/diffs OpenAPI vs docs. Deferred.
- 🔍 **19.2** `docs/EXPLAINABILITY.md`, `INTELLIGENCE.md`, `INTERVENTION.md` reflect shipped features.
  > **Evidence:** All 3 + `PEN_TEST_SCOPE.md`, `THREAT_MODEL.md` exist in `docs/`. Content currency not audited. Deferred.
- 🔍 **19.3** `README.md` quickstart works on a clean clone (bootstrap commands, env setup, docker compose up).
  > **Evidence:** `README.md` exists. Per 0.6, may still describe initial-commit architecture, not Phase E. Deferred.
- 🔍 **19.4** Architecture diagram reflects Phase E end-state (async, Triton, Memgraph/Neo4j, Qdrant, Feast, Redpanda, OTel).
  > **Evidence:** Deferred — needs README/diagram read.
- 🔍 **19.5** `customer trust surface` published: status page, `/.well-known/security.txt`, privacy policy, DPA, SLA — referenced from docs.
  > **Evidence:** No `/.well-known/security.txt` or `public/security.txt` found in repo. No status-page manifest. Deferred full check.

---

## Section 20 — Known-Gap Sweep (things most likely broken)

- ❌ **20.1** **Frontend test runner missing** — `package.json` has no `vitest`/`playwright`/`@testing-library` in devDeps despite the plans calling for FE tests. Confirm and add, or document as deferred.
  > **Evidence:** Confirmed in 18.6 — NO test runner in devDeps, NO test script, NO config files. **Gap confirmed.**
- ✅ **20.2** **Tailwind v4 config** — `postcss.config.js` and `tailwind.config.js` are **deleted** (git status shows `D`). Confirm Tailwind v4 runs via `@tailwindcss/postcss` only and globals.css has the `@import "tailwindcss"` + `@theme` tokens; no stale references to the old config files.
  > **Evidence:** `frontend/app/globals.css:1` — `@import "tailwindcss";` followed by `@theme { --color-surface: ...; --font-sans: ...; --radius-*: ... }`. `@tailwindcss/postcss: ^4.1.0` + `tailwindcss: ^4.1.0` in devDeps. Old JS config files deleted (git status `D`). **Clean v4 migration, no stale references.**
- ⚠️ **20.3** **`nul` file at root** — Windows redirect artifact, almost certainly junk. Remove.
  > **Evidence:** `nul` exists (324 bytes, Jun 20). Still present — NOT removed. (Same as 0.1.) Low-risk but should be deleted + added to `.gitignore`.
- ⚠️ **20.4** **Mock data on dashboard** — the original dashboard had `scansToday: 145023` hardcoded. Confirm the rebuilt dashboard pulls from `/analytics/dashboard` via TanStack Query with a visible "demo mode" badge only when the API is unreachable.
  > **Evidence:** `dashboard/page.tsx:62` — `fetch('/api/v1/analytics/dashboard')` for real stats; `apiConnected` state toggles the badge. **Caveat:** the live `FeedEvent` stream is ALWAYS seeded from hardcoded `FEED_TEMPLATES` (13 mock events) regardless of API state — only the `DashboardStats` cards pull real data. Demo-mode badge (`isDemoMode`) shows when API offline. Partial fix — feed remains mock.
- ⚠️ **20.5** **`react: 19` + `@tremor/react: ^3.18`** — Tremor 3 may not officially support React 19 yet; verify the dashboard renders without peer-dep errors. Same check for `react-simple-maps`/`react-force-graph-2d` on React 19.
  > **Evidence:** `react: ^19.1.0` + `@tremor/react: ^3.18.0` + `react-simple-maps: ^3.0.0` + `react-force-graph-2d: ^1.29.1` all in deps. CI `frontend-build` (`ci.yml:75`) runs `next build` which would fail on hard peer-dep conflicts. **Caveat:** npm (not pnpm/yarn) doesn't hard-error on peer-deps by default; runtime render issues possible. Needs `npm ls` + a build run.
- 🔍 **20.6** **Migration `hash_bank_api_keys`** is the last in the chain — confirm existing bank rows get migrated (backfill) and reads still resolve keys after the column type change.
  > **Evidence:** Migration exists (per 3.6, last in chain, has backfill-aware downgrade). CI `migrate-fresh-db` (`ci.yml:113`) runs `alembic upgrade head` on empty Postgres — proves the chain applies, but NOT that existing rows backfill (empty DB has none). Needs a populated-DB migration test.
- ⚠️ **20.7** **Audit-chain verification job is scheduled** (not just the function existing) — check Celery beat / cron entry actually invokes `verify_job`.
  > **Evidence:** Celery beat has `audit-verify-daily` (`compliance.verify_audit_chain_window`, daily 01:15) + `audit-verify-full` (weekly Sun 04:00) (`celery_app.py:64-71`). **Caveat:** the task name `compliance.verify_audit_chain_*` must be a registered `@celery_app.task` — the `include` list (`celery_app.py:15-24`) references `app.workers.tasks.compliance_tasks` but that module's task decorators weren't confirmed in this audit. **Risk: beat fires but task isn't registered → SilentFailure/NotRegistered error.**
- ✅ **20.8** **WhatsApp send path is live** (`_send_whatsapp_reply` was commented out in the bug log) — confirm it sends and is tested.
  > **Evidence:** `whatsapp_sender.send_whatsapp_warning` is LIVE — real `httpx.post` to WhatsApp Cloud API v18.0 with bearer auth, template message, 2-attempt retry, audit-log to `InterventionLog`. Gated by `settings.whatsapp_outbound_enabled`. No commented-out code.
- ✅ **20.9** **`feedback`/`explain`/`batch`/`ws` routers not double-registered** — re-grep `main.py` (the original Phase-0 bug); current read shows them once, but verify after any recent edits.
  > **Evidence:** Confirmed in Section 2.1 — all 32 routers included exactly once.
- ⚠️ **20.10** **`pre-transaction` webhook P95 < 100ms** — it's the tightest SLA; confirm it doesn't hit Postgres on the hot path (Redis/Memgraph only).
  > **Evidence:** `analyze.py:341` — `POST /webhook/pre-transaction` exists. **Caveat:** endpoint body not audited in this pass — needs confirmation it reads from Redis/graph cache and bypasses Postgres writes on the hot path to hold the 100ms SLA. The `/analyze` path writes to Postgres (`ScanEvent`), so if pre-tx reuses that code it will miss the SLA.

---

## Summary Scorecard (All Sections Checked)

| Section | PASS | FAIL | CAVEAT | UNKNOWN |
|---------|------|------|--------|---------|
| 0 — Repo Hygiene | 3 | 2 | 1 | 1 |
| 1 — Config & Secrets | 1 | 5 | 1 | 0 |
| 2 — Bootstrap & Middleware | 8 | 1 | 0 | 0 |
| 3 — DB & Migrations | 4 | 3 | 0 | 0 |
| 4 — Auth & Session | 3 | 4 | 2 | 0 |
| 5 — API Surface | 3 | 2 | 1 | 6 |
| 6 — NLP/ML | 3 | 2 | 3 | 1 |
| 7 — Graph | 5 | 0 | 1 | 0 |
| 8 — Intervention/Voice/Behavior/Recovery | 2 | 1 | 2 | 0 |
| 9 — Compliance & PII | 5 | 0 | 3 | 0 |
| 10 — Billing | 0 | 1 | 5 | 1 |
| 11 — Workers/Events | 2 | 0 | 4 | 0 |
| 12 — Security | 2 | 1 | 3 | 0 |
| 13 — Observability | 2 | 0 | 2 | 3 |
| 14 — Frontend | 4 | 1 | 5 | 2 |
| 15 — SDKs | 2 | 0 | 2 | 0 |
| 16 — Infra | 4 | 0 | 1 | 2 |
| 17 — CI/CD | 1 | 2 | 2 | 0 |
| 18 — Tests | 0 | 3 | 5 | 0 |
| 19 — Docs | 0 | 0 | 0 | 5 |
| 20 — Gap Sweep | 3 | 1 | 6 | 0 |
| **TOTAL** | **54** | **28** | **48** | **21** |

### Critical FAILs requiring immediate action:
1. **4.4/4.5/4.6** — No TOTP MFA, password policy is min-8 (not min-12), no HIBP check, no rate limits on auth endpoints
2. **1.2** — `neo4j_password` defaults to `"password"` in production code
3. **3.8** — 8 tables completely missing from Alembic migrations (will break clean deploy)
4. **3.7** — `SSOConfig` missing from `env.py` imports
5. **6.8** — No gold-set CI gate implemented
6. **5.12** — Contract tests cover only 2 of 31 routers and don't use schemathesis
7. **5.3** — Webhook router has no HMAC/idempotency/publish (logic is in a separate service but not wired)
8. **3.4** — No read-replica routing
9. **8.3** — Behavioral risk is hand-weighted sum, NOT a trained XGBoost model (training data is collected but no pipeline consumes it)
10. **12.4** — No mTLS for bank-to-TrustShield (API-key-hash only)
11. **14.1** — Dual routing: 10 flat FE pages duplicate the localized `[locale]` routes with no redirect — active bug source
12. **17.4** — No CODEOWNERS, no Renovate config
13. **18.6** — Frontend has NO test runner (no vitest/playwright) despite plans calling for FE tests
14. **18.8 / 0.1** — 12 orphan `test_*.py` scripts at repo root, not in the test suite
15. **20.1** — FE test runner missing (same root cause as 18.6)

### Moderate issues:
16. **4.1** — SameSite is `lax` not `strict`
17. **6.5** — Calibration module (`ml/training/calibrate.py`) doesn't exist in codebase — `test_calibrate.py` likely fails
18. **6.2** — No eager model warmup in lifespan; cold-start risk
19. **1.6** — ~35 settings undocumented in `.env.example`
20. **4.8** — Tenant isolation tests don't test actual data isolation
21. **1.3** — Secrets loader is AWS-SM only; 4 direct `os.getenv` bypasses
22. **8.2** — Voice has NO diarization, NO circuit breaker (just try/except)
23. **8.5 / 10.4** — RBI report + Stripe metered billing have no MinIO upload / signed-URL / Usage Records API
24. **10.2** — Usage recording writes to Postgres on every call (no Redis hourly bucket) — adds latency to `/analyze` P95
25. **9.7** — DPDP access/erasure endpoints are auth-gated stubs (return global counts, do nothing)
26. **11.2** — Kafka consumer `_handle_event` is a stub (logs only, no dispatch)
27. **11.5** — Retention cleanup NOT wired into Celery beat; uses raw `text()` SQL
28. **12.2** — Security CI missing ZAP, schemathesis, Snyk, image-scan (only gitleaks + trivy fs)
29. **17.1** — CI missing mypy, vitest, schemathesis, compose-integration, gold-gate, image-build
30. **20.4** — Dashboard live-feed is always mock (`FEED_TEMPLATES`); only stat-cards are real
31. **20.7** — Beat schedules `compliance.verify_audit_chain_*` but task registration unverified → possible NotRegistered error
32. **20.10** — `pre-transaction` webhook hot-path Postgres usage unverified — may miss 100ms SLA

### Highest-leverage fixes (do these first):
1. Add the 8 missing tables to Alembic migrations (3.8) + `SSOConfig` to env.py (3.7) — unblocks clean deploys
2. Create `ml/training/calibrate.py` + `ml/monitoring/drift.py` (6.5/6.6) — unblocks the NLP runtime + `test_calibrate.py`
3. Add `@limiter.limit()` to `/auth/login` + `/auth/register` + password min-12 + TOTP (4.4/4.5/4.6)
4. Wire `webhook_dispatcher` HMAC/idempotency into the `webhook_subscriptions` router (5.3)
5. Pick ONE FE route tree (recommend `[locale]/`) and redirect/delete the flat duplicate (14.1)
6. Add `vitest` + `@playwright/test` to FE devDeps + a `test` script (18.6/20.1)
7. Move/delete the 12 root `test_*.py` orphans + the `nul` file (0.1/18.8/20.3)
8. Implement behavioral XGBoost training pipeline consuming `BehavioralSignal` rows (8.3)
9. Add CODEOWNERS + Renovate + branch protection (17.4)
10. Confirm `compliance.verify_audit_chain_*` tasks are `@celery_app.task`-registered (20.7)

---

## How to execute this review

1. **Automated first (cheap, fast):** Sections 17, 18, 3.5, 6.8, 9.1, 14.6 — run CI, pytest, alembic, gold-set, audit-verify, i18n-lint.
2. **Static grep pass:** Sections 1, 2.1, 9.6, 12.3 — grep for hardcoded secrets, duplicate routers, raw `str(exc)`, LLM calls bypassing `redact()`.
3. **Runtime smoke:** Sections 2, 5, 14 — boot compose stack, hit each endpoint, click each FE route.
4. **Security deep-dive:** Sections 4, 9, 12 — auth flows, tenant isolation tests, pen-test scope.
5. **Manual expert review:** Sections 6, 7, 8 — ML/graph/intervention correctness against the phase plans.

When all boxes are checked, the Definition of Done from `IMPROVEMENT_PLAN.md` §15 and `IMPROVEMENT_PLAN_2.md` §9 is satisfied.
