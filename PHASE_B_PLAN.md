# TrustShield — Phase B Implementation Plan: Revenue-Ready

> **Status:** Planning document — NO code in this file. This is an execution spec for a coding agent.
> **Prerequisite:** Phase A is complete (auth hardening, secret mgmt, production data layer, bank onboarding, customer trust surface — see `IMPROVEMENT_PLAN_2.md` §3). The bug audit of 2026-06-19 (BUGFIX_LOG.md) is fixed.
> **Goal of Phase B:** Charge for usage, ship real ML in production, and produce compliance evidence on demand. Four pillars: **B1 Billing & Metering**, **B2 Real ML in Production**, **B3 Compliance Evidence Pipeline**, **B4 PII & Encryption**.
> **Exit gate:** First paying customer onboarded with metered billing; gold-set F1 ≥ 0.90; audit-chain verification green for 30 days; DPDP data register published; RBI submission receipt persisted on ≥1 recovery case.

---

## 0. How to Read This Plan (for the executing agent)

- **Build order matters.** Pillars are ordered B1 → B4 for dependency reasons. B1 (billing) touches the request path and must land before B4 (PII encryption) rewrites column storage. B2 (ML) is independent and can proceed in parallel after B1's schema is merged. B3 (compliance) consumes data produced by B1, B2, B4 — do it last.
- **Every task has a Location, Action, and Verification.** Location = exact file path(s) to create or modify. Action = what to change in prose (NO code). Verification = how to prove it works (test name, endpoint, CI check).
- **Match existing conventions.** The backend uses FastAPI + SQLAlchemy 2.0 async (`AsyncSession`), Pydantic v2, Alembic migrations, `app.services.<domain>` layout, `require_role` for authz, `verify_bank_api_key` for bank auth. The frontend uses Next.js app router, `lib/api.ts` ApiClient, `lib/auth.ts` AuthProvider. Match import style, logging (`logger = logging.getLogger(__name__)`), and the hash-chain audit pattern already in `audit_service.py`.
- **Every new model needs:** (a) an import in `backend/alembic/env.py`, (b) an import in `backend/app/database.py` `init_db()`, (c) an Alembic migration in `backend/alembic/versions/` chained off the current head (`f2b3c4d5e6f7` after Phase A). Check `alembic upgrade head` runs clean after each model lands.
- **No default secrets.** Any new config in `backend/app/config.py` must be empty-string default and the startup check in `backend/app/main.py` lifespan must reject empty secrets in non-dev environments.
- **Definition of Done per task:** migration applies cleanly, unit test in `backend/tests/unit/` passes, integration test in `backend/tests/integration/` passes, `ruff check .` is clean, and the endpoint returns the documented status code.

---

## Pillar B1 — Billing & Metering

**Objective:** Every billable API call is counted, enforced against a plan limit, and reported to Stripe so an invoice is generated correctly. A bank can subscribe, hit limits, upgrade, and get billed end-to-end without founder intervention.

### B1.1 — Configuration & Secrets

- **Location:** `backend/app/config.py` (modify), `backend/.env.example` (modify), root `.env.example` (modify).
- **Action:** Add settings fields to the `Settings` class: `stripe_secret_key: str = ""`, `stripe_webhook_secret: str = ""`, `stripe_price_id_free: str = ""`, `stripe_price_id_pro: str = ""`, `stripe_price_id_bank: str = ""`, `stripe_price_id_enterprise: str = ""`, `billing_enabled: bool = False`. Keep all defaults empty/False so dev is unaffected. Add `stripe>=8.0.0` to `backend/requirements.txt`. Update the lifespan startup check in `backend/app/main.py` to fail-fast in non-dev if `billing_enabled and not stripe_secret_key`.
- **Verification:** App boots in dev with `billing_enabled=False`. In a fake prod env (`environment=production`, `billing_enabled=True`, empty stripe key), startup raises `SystemExit(1)`.

### B1.2 — Database Models (Subscriptions, Plans, Usage Ledger)

- **Location:** create `backend/app/models/billing.py`.
- **Action:** Define four models following the existing column style (Integer PK, `String` with lengths, `DateTime(timezone=True)` with `server_default=func.now()`):
  1. **`Plan`** (`__tablename__="billing_plans"`): `code` (String(20), unique — "free"|"pro"|"bank"|"enterprise"), `name` (String(50)), `monthly_scan_limit` (Integer, -1 = unlimited), `monthly_webhook_limit` (Integer, -1), `price_id_stripe` (String(100), nullable), `sla_percent` (Float, e.g. 99.9), `features_json` (Text — JSON of feature flags), `is_active` (Boolean default True).
  2. **`Subscription`** (`billing_subscriptions`): `bank_id` (String(36), FK to `intel_banks.bank_id`, indexed, nullable=True — can be bank or user-scoped), `user_id` (Integer, indexed, nullable=True), `plan_code` (String(20)), `stripe_customer_id` (String(100), nullable), `stripe_subscription_id` (String(100), nullable), `status` (String(20) — "trialing"|"active"|"past_due"|"canceled"), `current_period_end` (DateTime), `created_at`, `updated_at`.
  3. **`UsageLedger`** (`billing_usage_ledger`): `subscription_id` (Integer, FK), `bucket` (String(20) — "YYYY-MM" roll-up key), `scan_calls` (Integer default 0), `webhook_calls` (Integer default 0), `last_call_at` (DateTime). Unique constraint on `(subscription_id, bucket)`.
  4. **`UsageEvent`** (`billing_usage_events` — raw event log for dispute resolution): `subscription_id` (Integer, indexed), `endpoint` (String(50) — "analyze"|"webhook"), `session_id` (String(100)), `created_at`. This is append-only; retention 13 months (per Stripe tax best practice), documented in the retention job (B1.8).
- **Wiring:** Add all four imports to `backend/alembic/env.py` and `backend/app/database.py init_db()`.
- **Verification:** New Alembic migration applies; `alembic upgrade head` is clean; the four tables exist in the dev SQLite DB.

### B1.3 — Alembic Migration

- **Location:** create `backend/alembic/versions/<new_rev>_add_billing.py`, with `down_revision = "f2b3c4d5e6f7"` (the Phase A api_key_hash migration head).
- **Action:** `op.create_table` for each of the four models above. Add indexes and the unique constraints named consistently (prefix `ix_`/`uq_`/`pk_`). `downgrade()` drops in reverse FK order (UsageEvent → UsageLedger → Subscription → Plan). In `upgrade()` also seed the four default `Plan` rows via `op.bulk_insert` with the tier limits from IMPROVEMENT_PLAN_2 §4.B1 (Free 1k scans, Pro 50k, Bank 1M, Enterprise -1).
- **Verification:** `alembic upgrade head` then `alembic downgrade -1` then `upgrade head` — both directions work.

### B1.4 — Billing Service Layer

- **Location:** create `backend/app/services/billing/__init__.py`, `backend/app/services/billing/plan_service.py`, `backend/app/services/billing/usage_service.py`, `backend/app/services/billing/stripe_service.py`.
- **Action:**
  - **`plan_service.py`:** pure functions to look up a `Plan` by code, resolve the effective subscription for a bank_id or user_id (latest active row), and return the applicable limits. No Stripe calls.
  - **`usage_service.py`:**
    - `async def record_usage(db, subject_type, subject_id, endpoint) -> None` — increments the monthly `UsageLedger` row (upsert on conflict) and inserts a `UsageEvent`. Wrap in a single transaction. Designed to be called from middleware, so it must be fast and never raise into the request path (catch+log internally).
    - `async def get_usage(db, subscription_id, bucket) -> dict` — returns `{scan_calls, webhook_calls, scan_limit, webhook_limit, remaining_scan, remaining_webhook, percent_used}`.
    - `async def check_quota(db, subject_type, subject_id, endpoint) -> tuple[bool, Optional[dict]]` — returns `(allowed, quota_info)`. Enterprise plan (limit -1) always allowed. Uses the monthly bucket. Returns the info dict used to build the 429 response.
  - **`stripe_service.py`:** thin wrapper over the `stripe` Python lib. Functions: `create_checkout_session(bank_id, price_id, success_url, cancel_url)`, `create_billing_portal_session(stripe_customer_id, return_url)`, `construct_webhook_event(payload, sig_header)`, `handle_subscription_updated(event)`, `handle_invoice_paid(event)`, `sync_subscription_from_stripe(stripe_sub_id) -> Subscription`. All Stripe calls wrapped in try/except with logging; never let a Stripe outage 500 the API (billing failures must degrade to "allow + alert", not "block customers").
- **Verification:** Unit tests in `backend/tests/unit/test_usage_service.py` covering: quota check for a free plan at limit (returns False), enterprise plan (always True), usage recording increments correctly, upsert on second call in same month.

### B1.5 — Billing Middleware / Dependency

- **Location:** create `backend/app/middleware/billing.py`, register in `backend/app/main.py` AFTER `AuditMiddleware`.
- **Action:** A FastAPI dependency `enforce_billing_quota(endpoint: str)` (preferred over global middleware so it's applied per-route via `Depends`, matching the existing `verify_api_key` pattern). It: (1) resolves the caller (bank via `verify_bank_api_key` OR user via `get_current_user` — accept whichever is present; for unauthenticated public endpoints skip), (2) calls `check_quota`, (3) on deny raises `HTTPException(429)` with headers `Retry-After` (seconds until period end) and `X-Tier-Upgrade-URL` (the Stripe portal). On allow, fire-and-forget `record_usage` (use `asyncio.create_task` so it doesn't add latency, mirroring how `analyze.py` already does fire-and-forget for broadcasts).
- **Apply to billable routes:** `/api/v1/analyze` (analyze.py), `/api/v1/webhook/pre-transaction` (analyze.py), `/api/v1/analyze/batch` (batch.py — count as N usages where N=len(sessions), or one "batch" call — decide: **count batch as 1 call but meter each sub-session as a UsageEvent** so the ledger is accurate; document the choice in the route's docstring). Leave `/health`, `/auth/*`, `/intel/register-bank`, `/metrics`, docs routes exempt.
- **Verification:** Integration test `backend/tests/integration/test_billing.py`: a bank on the free plan making the 1001st `/analyze` call in a month gets 429 with `Retry-After` header; an enterprise bank is never throttled.

### B1.6 — Billing API Endpoints

- **Location:** create `backend/app/api/v1/billing.py`, register router in `backend/app/main.py` (`app.include_router(billing_router, prefix="/api/v1", tags=["Billing"])`).
- **Action:** Endpoints (all require auth — bank or user):
  - `GET /billing/usage` — current month usage + limits for the caller (uses `usage_service.get_usage`).
  - `GET /billing/subscription` — current plan, status, period end, Stripe IDs.
  - `POST /billing/checkout` — body `{price_id, success_url, cancel_url}` → returns Stripe Checkout URL via `stripe_service.create_checkout_session`.
  - `POST /billing/portal` — returns Stripe Customer Portal URL for self-serve plan management.
  - `GET /billing/plans` — public-ish (auth required) list of available plans for the upgrade UI.
- Pydantic schemas in the same file, following the `BankRegistrationRequest`/`Response` pattern in `intel.py`.
- **Verification:** `GET /billing/usage` returns 200 with correct shape for an authenticated bank; `POST /billing/checkout` returns a Stripe URL when `stripe_secret_key` is set and a graceful error when not.

### B1.7 — Stripe Webhook Endpoint

- **Location:** add to `backend/app/api/v1/billing.py`.
- **Action:** `POST /billing/stripe-webhook` — this is the ONE endpoint that must NOT require auth (Stripe calls it) and must NOT be behind the rate limiter. Read raw body (use `await request.body()`, not a Pydantic model — Stripe needs the raw bytes), verify the signature with `stripe_webhook_secret` via `stripe_service.construct_webhook_event`, return 400 on bad signature. Handle events: `checkout.session.completed` (create/sync Subscription), `customer.subscription.updated`/`deleted` (update status), `invoice.paid` (mark period). Log every webhook to the audit chain (the existing `AuditMiddleware` will catch it, but also write an explicit audit entry with the event type). Make it **idempotent** (Stripe retries): key off `stripe_subscription_id` + event id; store processed event ids in a small table or Redis set to dedupe.
- **Wiring:** Add `/billing/stripe-webhook` to the SKIP list in any rate-limit config. Ensure CORS allows Stripe's IP range (Stripe webhooks come from documented IPs — optionally validate against Stripe's published IP list as defense-in-depth, but signature verification is the real control).
- **Verification:** Integration test with a forged signature returns 400; a validly-signed (test-mode) event updates the subscription status in the DB. Add a test fixture that posts a sample Stripe event JSON.

### B1.8 — Nightly Usage Rollup & Retention

- **Location:** create `backend/app/services/billing/jobs.py`, wire into a Celery task or a simple background task launched in lifespan (the codebase already has Celery in requirements and `infra/helm` references workers — use the existing Celery infra if present, else an `asyncio` background loop started in `lifespan`).
- **Action:**
  - **Nightly rollup:** at 00:05 UTC, for each subscription, sum `UsageEvent` rows for the current month bucket and reconcile against `UsageLedger` (corrects any fire-and-forget drops). Report a metric `billing_meter_lag_seconds` if the count diverges beyond a threshold.
  - **Stripe metering submission:** if `billing_enabled`, push the monthly aggregate to Stripe as a usage record on the subscription's metered price (the "per-call" meter). This is what makes the invoice correct.
  - **Retention:** delete `UsageEvent` rows older than 13 months; keep `UsageLedger` indefinitely (small). Respect the `dpdp` retention philosophy.
- **Verification:** A unit test that seeds 5 UsageEvents, runs the rollup, asserts the ledger matches; a test that sets `created_at` 14 months ago and asserts it's deleted.

### B1.9 — Frontend Billing UI

- **Location:** create `frontend/app/dashboard/billing/page.tsx`, add nav link in `frontend/app/dashboard/page.tsx` or the layout nav, add API methods to `frontend/lib/api.ts`.
- **Action:** A "Billing" page (client component) that: (1) calls `GET /billing/usage` and renders a usage bar (used/limit per endpoint), (2) shows current plan card, (3) "Upgrade" / "Manage subscription" buttons that hit `POST /billing/checkout` and `POST /billing/portal` and redirect to the returned Stripe URLs. Follow the existing component style (Tailwind, the `StatCard`/`ErrorBoundary`/`Skeleton` components already in `frontend/components`). Add `getUsage()`, `getSubscription()`, `createCheckout(priceId)`, `createPortal()` methods to the `ApiClient` in `lib/api.ts` using the existing `fetch<T>` helper (which already sets `credentials: 'include'`).
- **Verification:** Page renders with a skeleton while loading, shows usage, upgrade button redirects to a Stripe URL (in test mode).

---

## Pillar B2 — Real ML in Production

**Objective:** Replace the keyword fallback as the live path with a trained, calibrated, monitored two-tier model (IndicBERT transformer + XGBoost GBM), validated by a CI gold-set gate and served with graceful fallback. A promoter worker does shadow-mode validation before any hot swap.

### B2.1 — Training Data & Pipeline Cleanup

- **Location:** `backend/ml/training/train.py` (rewrite the placeholder), `backend/ml/training/train_transformer.py`, `backend/ml/training/train_gbm.py`, `backend/ml/training/run_pipeline.py`, `backend/ml/data/`.
- **Action:** The current `train.py` is a TF-IDF+LogReg placeholder that does NOT match the production serving code (`classifier.py` expects ONNX transformer + ONNX GBM). **Make `run_pipeline.py` the single entry point** that orchestrates: load train/val/gold from `ml/data/*.json` → train transformer (IndicBERT fine-tune via `train_transformer.py`) → train GBM (`train_gbm.py`) → export both to ONNX (`export_onnx.py`) → evaluate on gold set → write `ml/artifacts/transformer/` and `ml/artifacts/gbm/` with `model.onnx`, `config.json` (label_map, model_version), `tokenizer.json`, `feature_names.json`, `metrics.json`. Log everything to MLflow via `mlflow_config.log_training_run` (already exists). The pipeline must be deterministic (set seeds) and runnable as `python -m ml.training.run_pipeline`.
- **Existing assets to use:** `ml/data/gold_set.json`, `train.json`, `val.json` already exist. `ml/training/features.py` has `extract_features`/`get_feature_names`/`conversations_to_feature_matrix`. `ml/monitoring/drift.py` has PSI. `mlflow_config.py` has logging.
- **Verification:** `python -m ml.training.run_pipeline` produces artifacts in `ml/artifacts/{transformer,gbm}/`; `metrics.json` reports macro-F1; MLflow run is logged. The `ModelLoader.load()` in `model_loader.py` then reports `transformer_available=True, gbm_available=True` on app boot.

### B2.2 — Calibration Layer

- **Location:** create `backend/ml/training/calibrate.py`, integrate into `run_pipeline.py`, store `calibration.json` next to the model (a `ml/data/calibration.json` stub already exists — replace with the real one).
- **Action:** After training the transformer, fit an **isotonic regression** calibrator on the validation set's predicted probabilities vs. true labels (per-class one-vs-rest, or a Platt sigmoid — isotonic preferred for the F1 target). Save the calibrator (joblib or ONNX). At inference, the `ScamClassifier._classify_transformer` must apply the calibrator to the softmax logits BEFORE returning `confidence`. This is critical because the intervention thresholds and the FP-rate SLA depend on `confidence` being a real probability.
- **Wiring:** `model_loader.py` loads `calibration.pkl` alongside `model.onnx` when present; expose `self.calibrator` on `ModelLoader`. `classifier.py` checks `loader.calibrator is not None` and applies it.
- **Verification:** Unit test: uncalibrated probs vs calibrated probs on a held-out set; calibrated confidence on a known-positive set should be within ±0.05 of the empirical positive rate (reliability check). The `ml/data/calibration.json` is regenerated by the pipeline.

### B2.3 — Gold-Set CI Gate

- **Location:** create `backend/ml/training/gold_eval.py`, add a CI job to `.github/workflows/ci.yml`.
- **Action:** A script `python -m ml.training.gold_eval --artifacts ml/artifacts --gold ml/data/gold_set.json` that loads the ONNX models, runs them on the gold set, and computes macro-F1, per-class F1, and FP-rate (legitimate→scam). Writes a `gold_report.json`. The CI job runs this on every PR touching `backend/ml/**` or `backend/app/services/nlp/**` and **fails the build** if macro-F1 regresses by more than 1 point below the committed baseline (store baseline in `backend/ml/baseline/gold_baseline.json`) OR if FP-rate exceeds 2%. Provide a `--update-baseline` flag for intentional model improvements (requires human review of the diff).
- **Verification:** CI job runs; a PR that degrades the model fails; `gold_report.json` is uploaded as a CI artifact.

### B2.4 — Model Serving & Graceful Fallback

- **Location:** `backend/app/services/nlp/classifier.py` (already has the tiered fallback — harden it), `backend/app/services/nlp/model_loader.py`.
- **Action:** The tiered fallback (transformer → GBM → keywords) is already structurally correct. Harden: (1) add a **50ms timeout** around the transformer inference (use `asyncio.wait_for`); on timeout, fall through to GBM. (2) Count fallback events as a Prometheus counter (`model_fallback_total{tier="keyword"}`) so ops can see how often the real model is NOT being used. (3) Apply the calibrator (B2.2). (4) Eager-load the model in `lifespan` (today `ModelLoader.load()` is lazy via `_get_loader` — call `ModelLoader().load()` explicitly in the lifespan startup so the first request isn't slow). Note: the IMPROVEMENT_PLAN mentions optional Triton/BentoML serving — **defer that to Phase C**; in-process ONNX runtime is correct for Phase B volume.
- **Verification:** Unit test that a slow/missing transformer falls through to GBM then keywords with the counter incremented; a test that the calibrator is applied when present.

### B2.5 — Drift Monitoring Job

- **Location:** create `backend/app/services/ml/drift_worker.py` (or extend `ml/monitoring/drift.py` with a runner), wire into the Celery/background task infra used in B1.8.
- **Action:** Nightly job: (1) pull the baseline distribution (the training-set prediction probabilities, stored as `ml/artifacts/baseline_probs.npy` by the training pipeline), (2) pull the last 7 days of prediction probabilities from `scan_events` (the model's `confidence` needs to be persisted — **add a `model_confidence` Float column to `ScanEvent`** via migration, written in `analyze.py`), (3) compute PSI per the existing `drift.compute_prediction_drift`, (4) write rows to `drift_log` (table exists — `DriftLog` model), (5) if any PSI > 0.2, page via the alerting service (`alert_service.trigger_alert`-style) and surface on the Explainability dashboard (the `explain.py` `/explain/drift` endpoint already returns a `DriftResponse` — wire it to read real `drift_log` rows instead of the placeholder empty list).
- **Migration:** Add `model_confidence` Float (nullable) to `scan_events`. Update `analyze.py` to write it. Update `ScanEvent` model.
- **Verification:** Nightly job writes `drift_log` rows; `/explain/drift` returns real feature/PSI data; a unit test seeds synthetic distributions with known PSI and asserts the computed value.

### B2.6 — Shadow Mode & Promotion Worker

- **Location:** create `backend/app/services/ml/promotion.py`, `backend/app/services/ml/shadow.py`.
- **Action:**
  - **Shadow mode:** a flag/config `model_shadow_version` that, when set, causes `classify()` to ALSO run the shadow model in parallel (not on the hot path — via `asyncio.create_task`), log the shadow prediction to a `shadow_predictions` table (new model: session_id, primary_pred, primary_conf, shadow_pred, shadow_conf, created_at), but return the primary model's result. After 7 days, compare agreement rate and gold-set metrics.
  - **Promotion worker:** `promote_model(new_version)` — a guarded call to `ModelRegistry.hot_swap` (already exists). The guard: (1) gold-set F1 of new ≥ gold-set F1 of current, (2) shadow agreement ≥ 95% over the window, (3) no regression in FP-rate. Only then flip `is_active` in `model_params` and call `hot_swap`. Expose `POST /model/promote` (admin-only via `require_role("super_admin")`) that runs the guard and either promotes or returns the rejection reason.
  - **New model:** `ShadowPrediction` in `backend/app/models/ml.py` (or add to an existing models file). Migration + env.py + init_db wiring.
- **Verification:** Unit test that the promotion guard rejects a worse model and accepts a better one; shadow predictions are logged but don't affect the returned result.

---

## Pillar B3 — Compliance Evidence Pipeline

**Objective:** Compliance artifacts are generated and verified automatically, not assembled by hand under audit pressure. The audit chain is verified nightly; a DPDP data register is maintained; RBI/1930 submission receipts are persisted; a one-click quarterly attestation bundle is producible.

### B3.1 — Audit Chain Nightly Verification

- **Location:** create `backend/app/services/audit/verify_job.py`, wire into the background-task infra.
- **Action:** Nightly job that calls the existing `audit_service.verify_chain(db)` over the full table (or the last day's window for speed, plus a weekly full-chain pass). If ANY entry is `valid=False`: (1) log CRITICAL, (2) page via alerting (PagerDuty/Slack hook — reuse `ALERT_WEBHOOK_URL` or add a dedicated `audit_alert_webhook`), (3) write a row to a new `audit_chain_breaks` table (model: id, first_bad_entry_id, expected_hash, actual_hash, detected_at, resolved_at). The break must NOT be auto-corrected (tamper evidence is the point) — it requires human ack via an admin endpoint `POST /audit/ack-break`.
- **Verification:** Unit test: insert a tampered row, run the job, assert a `audit_chain_breaks` row is created and the alert fires. Integration test of the ack endpoint.

### B3.2 — DPDP Data Register

- **Location:** create `backend/app/services/compliance/dpdp_register.py`, `backend/app/api/v1/dpdp.py` (add endpoint), `backend/app/models/compliance.py`.
- **Action:**
  - **Model `DataAsset`** (`dpdp_data_register`): `asset_name` (String — "recovery_cases.victim_phone"), `table_name`, `column_names` (Text, JSON list), `pii_category` (String — "contact"|"financial"|"identity"|"behavioral"), `lawful_basis` (String — "consent"|"legal_obligation"|"legitimate_interest"), `retention_policy` (String — "7 years per RBI"), `storage_location` (String — "ap-south-1 RDS, encrypted"), `shared_with` (Text, JSON), `last_reviewed` (DateTime), `dpo_contact` (String). This is the machine-readable inventory DPDP §8 requires.
  - **Service:** `build_register(db) -> list[DataAsset]` — assembles the register from the actual schema (can be a curated seed + a reflection pass). `export_register_json()` and `export_register_pdf()` for the DPO.
  - **Endpoint:** `GET /dpdp/register` (admin/DPO role only via `require_role`) returns the register; `GET /dpdp/register/export` returns a signed PDF.
  - **Seed:** bulk-insert rows covering `recovery_cases` (victim_name/phone, 7yr), `feedback_labels` (analyst_email, 2yr), `behavioral_signals` (device_fingerprint, 180d per config), `scan_events` (session_id, 730d), `intel_*` (hashed entity, indefinite), `audit_logs` (indefinite).
- **Verification:** Migration applies; `GET /dpdp/register` returns all seeded assets; the retention values match `config.py` (`retention_scan_events_days`, `retention_recovery_years`).

### B3.3 — RBI/1930 Submission Receipt Persistence

- **Location:** `backend/app/models/recovery.py` (modify), `backend/app/api/v1/recovery.py` (modify `submit_to_1930`), `backend/app/services/compliance/cybercrime_sandbox.py` (modify).
- **Action:**
  - Add columns to `RecoveryCase`: `cybercrime_ref_number` (String(50), nullable), `cybercrime_submitted_at` (DateTime, nullable), `cybercrime_submission_receipt` (Text, nullable — full JSON receipt), `cybercrime_status` (String(20), default "not_submitted"). Migration.
  - In `submit_to_1930` endpoint: after calling `submit_to_cybercrime`, **persist** the returned `reference_number` and full receipt onto the `RecoveryCase` row and commit. Return the persisted receipt in the response.
  - In `_real_submit` (the production path): make it actually POST to the configured `cybercrime_api_url` with the API key, capture the response (reference number, acknowledgment), and return it. Keep the sandbox path for dev. Document the manual fallback (if the real API is down, return a "manual_filing_required" status with the prefilled complaint PDF link — the PDF endpoint already exists).
  - Add `GET /recovery/{case_id}/submission-receipt` to fetch the persisted receipt.
- **Verification:** In sandbox mode, `submit_to_1930` persists `cybercrime_ref_number` on the case; the new GET endpoint returns it; a unit test of `_real_submit` against a mocked HTTP endpoint captures the receipt.

### B3.4 — Quarterly Attestation Bundle

- **Location:** `backend/app/services/compliance/export_pack.py` (already exists with CSV+ZIP), extend it; `backend/app/api/v1/dpdp.py` or a new `backend/app/api/v1/compliance.py`.
- **Action:** The existing `generate_regulator_pack(db, quarter)` produces entities/sessions/feedback/audit CSVs + a signed manifest in a ZIP. **Extend** it to also include: (1) the audit-chain verification report (call `verify_chain` and include `audit_verification.csv` — entry_id, valid), (2) the drift report (query `drift_log` for the quarter → `drift_report.csv`), (3) the model gold-set report (`gold_report.json` from B2.3), (4) the DPDP register (`dpdp_register.json` from B3.2), (5) a cover PDF (reuse `RBIReportBuilder` from `rbi_report_builder.py`). Add the new files to the manifest's file hash map and signature. Expose `GET /compliance/attestation/{quarter}` (admin role) returning the ZIP with `Content-Disposition: attachment`.
- **Sign-off:** Add a `sign_manifest` step that requires the admin's user_id + a timestamp, written into the manifest, so the bundle is attributable.
- **Verification:** `GET /compliance/attestation/Q2_2026` returns a ZIP containing all named files; the manifest's signature validates; tampering any file invalidates the manifest (unit test).

---

## Pillar B4 — PII & Encryption

**Objective:** PII is tokenized/encrypted at rest so a DB dump does not expose victims; field-level encryption protects the highest-risk columns; every external LLM call is redacted through a single chokepoint. **Order:** do B4 after B1 so the billing schema isn't churned twice.

### B4.1 — PII Tokenization Service

- **Location:** create `backend/app/services/security/pii_vault.py`, extend `backend/app/utils/pii.py`.
- **Action:**
  - **`pii_vault.py`:** a tokenization layer backed by envelope encryption with a KMS-controlled master key. For Phase B without a real KMS, use a local AES-256-GCM key from config (`pii_encryption_key`, 32 bytes base64) with a clear migration path to AWS KMS/GCP KMS in Phase C (abstract behind a `KeyProvider` interface). Functions: `tokenize(value, type) -> token` (deterministic token for lookup-ability where needed, e.g., phone → HMAC-SHA256 with a pepper, stored alongside), `encrypt_field(value) -> ciphertext` (AES-GCM, non-deterministic), `decrypt_field(ciphertext) -> value`. Store the DEK-wrapped ciphertext.
  - **`pii.py`:** keep the masking functions (for logs/exports) and add `redact(text)` — the single chokepoint that removes phone/UPI/email/IFSC from any text before it leaves the system (e.g., before an LLM call). The existing `mask_text` is close; promote `redact` to be the canonical external-boundary function and audit every external call site uses it.
- **Config:** add `pii_encryption_key: str = ""` to `settings`; fail-fast in non-dev if empty and PII features are on.
- **Verification:** Unit tests: tokenize is deterministic for the same input+key; encrypt then decrypt round-trips; redact removes all PII patterns from a sample scam message.

### B4.2 — Field-Level Encryption on Models

- **Location:** `backend/app/models/recovery.py`, `backend/app/models/feedback.py`, SQLAlchemy event listeners in `backend/app/services/security/encryption_listeners.py`.
- **Action:** Encrypt at rest: `recovery_cases.victim_name`, `victim_phone`, `scammer_info`, `upi_id`; `feedback_labels.analyst_email`. Implement via SQLAlchemy `hybrid_property` + `before_insert`/`before_update`/`after_load` event listeners that call `pii_vault.encrypt_field`/`decrypt_field` transparently — so application code reads/writes plaintext and the DB stores ciphertext. **Migration challenge:** existing plaintext rows must be migrated (read plaintext, encrypt, write back) in a data migration. The migration script iterates rows in batches (to avoid locking the table), encrypts, and commits in chunks.
- **Backward compat:** if `pii_encryption_key` is empty (dev), the listeners are no-ops and store plaintext — so dev DBs keep working. Gate via a `pii_encryption_enabled` computed flag.
- **Verification:** After migration, a raw `SELECT victim_phone FROM recovery_cases` returns ciphertext; the API returns decrypted plaintext; a unit test of the listener round-trip.

### B4.3 — Encrypted Backups Verification

- **Location:** `infra/BACKUP_RUNBOOK.md` (modify), `backend/app/services/compliance/backup_audit.py` (create).
- **Action:** Document (in the runbook) that managed RDS encryption-at-rest is enabled (this is a infra/terraform change outside the codebase — note it as an infra prerequisite). Add a `backup_audit.py` job that queries the DB's backup status (for RDS via the AWS API; for dev, a no-op) and writes a `backup_status` row to the audit log weekly, so there's evidence backups are running and encrypted. This is the "verify" half — the IMPROVEMENT_PLAN says "verify" and this makes it checked.
- **Verification:** The job runs and writes an audit entry; in dev it logs "backup verification skipped (non-managed DB)".

### B4.4 — PII Redaction at External Boundaries

- **Location:** `backend/app/services/nlp/warning_generator.py`, `backend/app/services/explain/rag_chat.py`, `backend/app/services/voice/whisper_service.py`, any LLM call site.
- **Action:** Audit every place data leaves the system to an external service (LLM API, Whisper, alert webhook, Sentry). Each must pass through `pii.redact()`. Specifically: (1) `rag_chat.answer_question` before any LLM call (today it's template-only, but when the real LLM is wired it must redact the question and any retrieved session text), (2) `warning_generator` if it ever sends text to an LLM, (3) Sentry `before_send` hook — add a filter in `main.py` Sentry init that scrubs PII from breadcrumbs/extras (Sentry has built-in scrubbing but it must be configured). Add a test that asserts no raw phone/UPI/email appears in the output of these services.
- **Verification:** Unit test that feeds a PII-laden string through each boundary and asserts the external-facing payload contains no unredacted PII (regex check for phone/UPI patterns).

---

## Cross-Cutting Tasks (apply across all pillars)

### X1 — Tests

- **Unit tests** (`backend/tests/unit/`): one per new service — `test_usage_service.py`, `test_stripe_service.py`, `test_calibrate.py`, `test_gold_eval.py`, `test_pii_vault.py`, `test_dpdp_register.py`, `test_encryption_listeners.py`, `test_promotion.py`.
- **Integration tests** (`backend/tests/integration/`): `test_billing.py` (quota enforcement, webhook), `test_model_serving.py` (fallback chain), `test_compliance_export.py` (attestation bundle), `test_pii_encryption.py` (round-trip via API).
- **Pattern:** follow `tests/integration/test_auth.py` and `tests/conftest.py` (use `TestClient`, the existing fixtures). Add fixtures for a seeded bank + subscription.
- **Coverage gate:** add `pytest --cov=app --cov-fail-under=70` to `backend/pytest.ini` and the CI test job.

### X2 — CI Updates (`.github/workflows/ci.yml`)

- Add a **`model-gold-eval`** job (B2.3) that runs on `backend/ml/**` and `backend/app/services/nlp/**` changes.
- Add `--cov-fail-under=70` to the existing `backend-test` job.
- Add a **`migrate-check`** job: run `alembic upgrade head` against a throwaway SQLite DB to catch broken migrations.
- Add `stripe`, `cryptography` (for AES-GCM) to `backend/requirements.txt` and ensure CI installs them.

### X3 — Observability

- Add Prometheus counters: `billing_quota_denied_total{plan}`, `model_fallback_total{tier}`, `audit_chain_break_total`, `pii_decrypt_total`, `stripe_webhook_total{event_type}`. Register them alongside the existing `/metrics` setup in `main.py`.
- Add a Grafana dashboard spec (JSON in `infra/helm/` or `infra/dashboards/`) covering: usage by plan, quota denials, model tier usage + fallback rate, drift PSI over time, audit-chain status, billing meter lag.

### X4 — Documentation

- Update `README.md` with: how to run the training pipeline, how to configure Stripe (test mode), how to run the nightly jobs locally.
- Update `infra/DEPLOYMENT.md` with the new env vars (Stripe keys, PII key, ML artifact paths).
- Add `docs/BILLING.md` describing the metering model and how disputes are resolved (the UsageEvent ledger is the source of truth).

---

## Exit Gate Checklist (Phase B)

A coding agent or reviewer can tick each box only when the verification for that task passes:

- [ ] **B1:** A test bank subscribes to "Pro" via Stripe Checkout (test mode), makes 50k+1 `/analyze` calls, gets throttled at 50k with a 429 + upgrade URL, upgrades to "Bank", gets unthrottled, and the monthly invoice reflects metered usage.
- [ ] **B2:** `python -m ml.training.run_pipeline` ships transformer+GBM ONNX artifacts; `ModelLoader` loads them on boot; gold-set macro-F1 ≥ 0.90 and FP-rate ≤ 2% in CI; a nightly drift job writes to `drift_log` and `/explain/drift` returns real data.
- [ ] **B3:** Nightly audit-chain verification is green for 30 consecutive days (simulate by running the job 30× in a test); `GET /dpdp/register` returns the full inventory; `submit_to_1930` persists a receipt on a recovery case; `GET /compliance/attestation/Q2_2026` returns a valid signed ZIP.
- [ ] **B4:** Raw DB queries on `recovery_cases.victim_phone` return ciphertext; the API returns plaintext; a PII-laden string passed to any external service is redacted (tested).
- [ ] All new migrations apply via `alembic upgrade head` on a fresh DB.
- [ ] `ruff check .` clean; `npm run lint` clean; pytest suite green with ≥70% coverage; CI `model-gold-eval` job green.

---

## Dependency Graph (build order)

```
B1.1 (config) ──┬─→ B1.2 (models) ──→ B1.3 (migration) ──→ B1.4 (services) ──┬─→ B1.5 (middleware)
                │                                                     ├─→ B1.6 (API)
                │                                                     └─→ B1.7 (webhook)
                └─→ B1.8 (jobs)  ←─ B1.4
B1.9 (frontend) ←─ B1.6

B2.1 (pipeline) ──→ B2.2 (calibration) ──→ B2.4 (serving+calibrator)
                ──→ B2.3 (gold CI gate)
B2.4 ──→ B2.5 (drift job) [needs ScanEvent.model_confidence migration]
B2.4 ──→ B2.6 (shadow/promotion)

B3.1 (audit verify job)        [independent — do early]
B3.2 (DPDP register)           [independent]
B3.3 (1930 receipt)            [independent]
B3.4 (attestation bundle)      ←─ B2.3 (gold report) + B2.5 (drift) + B3.1 (audit) + B3.2 (register)

B4.1 (pii vault) ──→ B4.2 (field encryption) [do AFTER B1 to avoid double-migration]
B4.1 ──→ B4.4 (redaction)
B4.3 (backup audit) [independent]
```

**Recommended sequence:** B1.1→B1.2→B1.3→B1.4→B1.5→B1.6→B1.7 (billing vertical slice) ‖ B2.1→B2.2→B2.4→B2.3 (ML vertical slice) → B1.8, B2.5, B2.6 (jobs) → B3.1, B3.2, B3.3 (compliance) → B4.1→B4.2→B4.4 (PII) → B3.4 (attestation bundle, which ties everything together) → X1/X2/X3/X4 (tests, CI, observability, docs).
