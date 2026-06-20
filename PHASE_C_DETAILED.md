# TrustShield — Phase C Detailed Implementation Guide

> **Companion to `PHASE_C_PLAN.md`.** That file is the pillar-level spec (objective, dependency graph, exit gate). THIS file is the atomic, step-by-step execution breakdown — every task decomposed into ordered, concrete steps: exact files to touch, functions/classes to add, config keys, migration columns, test names + assertions, and the commands to verify.
> **Conventions (unchanged from Phase B):** FastAPI + SQLAlchemy 2.0 async (`AsyncSession`), Pydantic v2, Alembic, `app.services.<domain>` layout, `require_role` authz, `verify_bank_api_key`, Celery at `backend/app/workers/celery_app.py`. Frontend: Next.js app router, `lib/api.ts`, Tailwind. Infra: `infra/` (docker-compose + `infra/helm/trustshield/`).
> **Per-task DoD:** migration applies, unit + integration tests pass, `ruff check .` clean, the endpoint/cron/metric returns the documented result. Infra tasks must update BOTH `docker-compose.yml` (local) and the Helm chart (prod).
> **Step notation:** `▸` = action step, `✓` = verification step (command or test).

---

# Pillar C1 — Managed Infra & KMS

## C1.1 — KMS-Backed Key Provider

**Files:** create `backend/app/services/security/kms_provider.py`; modify `backend/app/services/security/pii_vault.py`, `backend/app/config.py`, `backend/app/main.py`.

**Steps:**

1. ▸ **Define the `KeyProvider` ABC** in `kms_provider.py`:
   - `class KeyProvider(ABC)` with two abstract methods: `async def generate_dek(self) -> tuple[bytes, bytes]` (returns `(plaintext_dek, wrapped_dek)`) and `async def unwrap_dek(self, wrapped_dek: bytes) -> bytes`.
   - Add `@abstractmethod async def master_key_id(self) -> str` for audit logging.

2. ▸ **Implement `LocalKeyProvider(KeyProvider)`** — the dev path. Wraps the existing `pii_encryption_key`. `generate_dek` returns `(derived_key, b"local:" + salt)` where `derived_key = HKDF(pii_encryption_key, salt)`; `unwrap_dek` re-derives from the salt. No network calls.

3. ▸ **Implement `KMSKeyProvider(KeyProvider)`** — the prod path. Uses `boto3.client("kms", region_name=settings.kms_region)`.
   - `generate_dek` → `kms.generate_data_key(KeyId=kms_key_id, KeySpec="AES_256")`, return `(Plaintext, CiphertextBlob)`.
   - `unwrap_dek` → `kms.decrypt(CiphertextBlob=wrapped)["Plaintext"]`.
   - Constructor takes optional `boto3_client` for test injection (moto).

4. ▸ **Refactor `pii_vault.py`** (Phase B version):
   - Replace the direct `pii_encryption_key` use with a `_get_provider()` resolver: returns `KMSKeyProvider` if `settings.kms_key_id` else `LocalKeyProvider`.
   - Change `encrypt_field` ciphertext format to **versioned envelope**: `bytes([1]) + len(wrapped_dek) as 1 byte + wrapped_dek + nonce + aesgcm_ciphertext + tag`. The version byte lets us detect legacy Phase B ciphertext (no prefix).
   - Add `_is_legacy(blob: bytes) -> bool` — legacy = no recognized version prefix.
   - **Lazy re-encryption:** in `decrypt_field`, if `_is_legacy`, decrypt with the old local key, then re-encrypt with the new envelope format and return `(plaintext, new_ciphertext)`; callers (the encryption listeners) write the new ciphertext back on next flush. Never block reads to re-encrypt a whole table.

5. ▸ **Config (`config.py`):** add `kms_key_id: str = ""`, `kms_region: str = "ap-south-1"`, `aws_access_key_id: str = ""`, `aws_secret_access_key: str = ""`. Add `boto3>=1.34.0` to `requirements.txt`.

6. ▸ **Startup check (`main.py` lifespan, after the Phase B block at ~L125-137):**
   ```
   if settings.environment != "development":
       if not settings.pii_encryption_key and not settings.kms_key_id:
           logger.critical("Either PII_ENCRYPTION_KEY or KMS_KEY_ID must be set in non-dev")
           raise SystemExit(1)
   ```

**✓ Verification:**
- Unit `tests/unit/test_kms_provider.py`:
  - `test_local_provider_roundtrip` — generate+unwrap returns same DEK.
  - `test_kms_provider_roundtrip` — using `moto.mock_aws` + a created KMS key, generate+unwrap round-trips.
  - `test_legacy_lazy_reencrypt` — seed a Phase B-format ciphertext, decrypt returns plaintext AND a versioned blob; re-decrypting the new blob needs no upgrade.
- `ruff check backend/app/services/security/`.

---

## C1.2 — Managed Postgres & Redis Connection Hardening

**Files:** modify `backend/app/config.py`, `backend/app/database.py`, `backend/app/main.py`; `infra/pgbouncer.ini`, `infra/docker-compose.yml`, `infra/helm/trustshield/values.yaml`, `infra/DEPLOYMENT.md`.

**Steps:**

1. ▸ **Config (`config.py`):** add `db_pool_size: int = 10`, `db_max_overflow: int = 20`, `db_pool_timeout: int = 30`, `db_pool_recycle: int = 1800`, `db_ssl_required: bool = True` (default True, dev overrides to False).

2. ▸ **`database.py` `create_async_engine`** — pass the pool kwargs explicitly:
   - `pool_size=settings.db_pool_size`, `max_overflow=settings.db_max_overflow`, `pool_timeout=settings.db_pool_timeout`, `pool_recycle=settings.db_pool_recycle`, `pool_pre_ping=True`.
   - For asyncpg, inject SSL via connect_args only when `db_ssl_required and environment != development`: `connect_args={"ssl": "require"}`.

3. ▸ **`main.py` startup check:**
   ```
   if settings.environment != "development":
       if not settings.database_url.startswith("postgresql+asyncpg://"):
           logger.critical("Non-dev must use postgresql+asyncpg"); raise SystemExit(1)
       if settings.db_ssl_required and "sslmode" not in settings.database_url and "ssl=require" not in settings.database_url:
           logger.critical("DB connection must require SSL in non-dev"); raise SystemExit(1)
       if settings.event_backend == "redis" and not settings.redis_url.startswith("rediss://"):
           logger.critical("Redis must use TLS (rediss://) in non-dev"); raise SystemExit(1)
   ```

4. ▸ **Complete `infra/pgbouncer.ini`:** `[databases]` → `trustshield = host=<rds_endpoint> port=5432 dbname=trustshield`, `[pgbouncer]` → `listen_addr = 0.0.0.0`, `listen_port = 6432`, `pool_mode = transaction`, `max_client_conn = 1000`, `default_pool_size = 25`, `reserve_pool_size = 5`, `server_idle_timeout = 600`, `auth_type = scram-sha-256`.

5. ▸ **Helm `values.yaml`:** add a `pgbouncer.enabled: true` toggle + a sidecar container spec; add `database.sslMode: require`, `redis.tls: true`.

**✓ Verification:**
- `tests/unit/test_database.py::test_engine_pool_config` — mock `create_async_engine`, assert the kwargs match config.
- `tests/unit/test_main_startup.py::test_non_dev_ssl_required` — fake prod config with non-SSL DB URL → `SystemExit(1)`.
- `cd infra && docker-compose config` validates.
- Dev boot unchanged (`environment=development` skips the checks).

---

## C1.3 — Secrets Management (AWS Secrets Manager)

**Files:** create `backend/app/services/security/secrets_loader.py`; modify `backend/app/config.py`, `backend/app/__init__.py` (or the earliest import point before `Settings()`).

**Steps:**

1. ▸ **`SecretsLoader` class** in `secrets_loader.py`:
   - `__init__(self, prefix: str, region: str, client=None)`.
   - `async def load(self) -> dict[str, str]` — calls `client.get_secret_value(SecretId=prefix)` (or iterates a list if multiple), parses each stored secret as JSON key/values, returns a flat dict.
   - `apply_to_environ(secrets: dict, overwrite=False)` — sets `os.environ` keys; if `overwrite=False`, skip keys already set (env wins).

2. ▸ **Hydration ordering** — `Settings()` is instantiated at `config.py:117`. Insert the loader BEFORE that: add a `_maybe_hydrate_secrets()` function called at module top (after imports), gated on `settings_secrets_prefix` env var read directly from `os.environ` (not pydantic, to avoid bootstrap paradox). Runs `asyncio.run(loader.load())` only once.

3. ▸ **Config (`config.py`):** add `secrets_manager_prefix: str = ""`, `secrets_manager_region: str = "ap-south-1"`.

4. ▸ **Expected secret names** (documented): `trustshield/<env>/db` → `{database_url}`, `trustshield/<env>/redis` → `{redis_url}`, `trustshield/<env>/app` → `{jwt_secret, pii_encryption_key, kms_key_id, stripe_secret_key, ...}`. Document mapping in `infra/SECRETS_RUNBOOK.md`.

**✓ Verification:**
- `tests/unit/test_secrets_loader.py::test_load_populates_environ` — moto `secretsmanager.create_secret`, call `_maybe_hydrate_secrets`, assert `os.environ["JWT_SECRET"]` set.
- `test_env_overrides_win` — pre-set `os.environ["JWT_SECRET"]`, load secrets with `overwrite=False`, assert unchanged.
- `test_dev_no_prefix_skips` — empty prefix → loader not invoked, no AWS call.

---

## C1.4 — Terraform for Managed Resources

**Files:** create `infra/terraform/` with `main.tf`, `versions.tf`, `variables.tf`, `outputs.tf`; modules `infra/terraform/modules/{rds,elasticache,s3,kms,secrets,ecr}/`; env files `infra/terraform/envs/staging.tfvars`, `envs/prod.tfvars`.

**Steps:**

1. ▸ **`versions.tf`:** Terraform ≥ 1.6, AWS provider ≥ 5.0, backend S3 (state bucket + DynamoDB lock — document creation as a one-time manual step in `infra/SECRETS_RUNBOOK.md`).

2. ▸ **`modules/kms/main.tf`:** one `aws_kms_key` (enable_key_rotation=true, multi_region optional), key policy allowing the API + worker IAM roles `kms:Encrypt/Decrypt/GenerateDataKey`; deny others. Output `key_id`, `key_arn`.

3. ▸ **`modules/rds/main.tf`:** `aws_db_instance` Postgres 16, `storage_encrypted = true` referencing the KMS key, `multi_az = true`, `backup_retention_period = 30`, `deletion_protection = true` (prod), parameter group with `log_statement = "ddl"`, `rds.log_connections = 1`. Output endpoint → Secrets Manager entry via `aws_secretsmanager_secret_version`.

4. ▸ **`modules/elasticache/main.tf`:** `aws_elasticache_replication_group` Redis 7, `transit_encryption_enabled = true`, `at_rest_encryption_enabled = true`, `auth_token` from a random password, `automatic_failover = true`, `num_cache_clusters = 2`. Output primary endpoint.

5. ▸ **`modules/s3/main.tf`:** two `aws_s3_bucket` — `ml-artifacts` (versioning + lifecycle: noncurrent after 90d to IA, 365d expire) and `backups` (versioning + `object_lock_configuration = GOVERNANCE`, retention 7y for compliance evidence). Both server-side encrypted with the KMS key.

6. ▸ **`modules/secrets/main.tf`:** `aws_secretsmanager_secret` per logical group (db, redis, app), each with an initial empty version; IAM policy grants the app role read.

7. ▸ **`modules/ecr/main.tf`:** `aws_ecr_repository` for `trustshield-api` and `trustshield-worker`, `image_scanning_configuration = true`, `lifecycle_policy` to keep last 10 + untagged purge after 7d.

8. ▸ **`main.tf`:** wire modules, pass env via `tfvars`. `outputs.tf` emits connection strings (marked sensitive).

**✓ Verification:**
- `cd infra/terraform && terraform init && terraform validate` → exit 0.
- `terraform plan -var-file=envs/staging.tfvars` → no errors, shows expected creates.
- Re-run `terraform plan` → **no diff** (idempotency).
- Manual: key policy review confirms only API/worker roles can decrypt.

---

# Pillar C2 — Job Scheduling & Workers

## C2.1 — Celery Beat Schedule

**Files:** modify `backend/app/workers/celery_app.py`; create `backend/app/workers/tasks/__init__.py`, `billing_tasks.py`, `ml_tasks.py`, `compliance_tasks.py`; modify `backend/app/config.py`.

**Steps:**

1. ▸ **Read the current `celery_app.py`** — it has a Celery app but no `conf.beat_schedule` and no registered tasks. Confirm `broker` = redis/kafka from config.

2. ▸ **`billing_tasks.py`** — thin wrappers (do NOT duplicate logic):
   - `@celery_app.task(bind=True, name="billing.nightly_rollup", soft_time_limit=300, max_retries=3) def nightly_usage_rollup(self): asyncio.run(_run(nightly_usage_rollup))` where `_run` opens an `AsyncSessionLocal` and calls the Phase B `app.services.billing.jobs.nightly_usage_rollup`.
   - Similarly `submit_stripe_metering` (calls `billing/jobs.py` Stripe submission), `purge_old_usage_events` (retention).
   - Retry decorator: `autoretry_for=(Exception,), retry_backoff=True, retry_backoff_max=600, retry_jitter=True`.

3. ▸ **`ml_tasks.py`:** `run_drift_check` → wraps `app.services.ml.drift_worker` (Phase B fixed). `soft_time_limit=600`.

4. ▸ **`compliance_tasks.py`:** `verify_audit_chain_window` (last 24h) and `verify_audit_chain_full` (weekly) → wrap `app.services.audit.verify_job`. `verify_backups` → `app.services.compliance.backup_audit`.

5. ▸ **`celery_app.py`** — add:
   ```
   from celery.schedules import crontab
   celery_app.conf.beat_schedule = {
       "nightly-usage-rollup": {"task":"billing.nightly_rollup","schedule":crontab(minute=5,hour=0)},
       "stripe-metering": {"task":"billing.submit_stripe_metering","schedule":crontab(minute=30,hour=0)},
       "usage-retention": {"task":"billing.purge_old_usage_events","schedule":crontab(minute=0,hour=3,day_of_week=0)},
       "drift-check": {"task":"ml.run_drift_check","schedule":crontab(minute=0,hour=1)},
       "audit-verify-daily": {"task":"compliance.verify_audit_chain_window","schedule":crontab(minute=15,hour=1)},
       "audit-verify-full": {"task":"compliance.verify_audit_chain_full","schedule":crontab(minute=0,hour=4,day_of_week=0)},
       "backup-audit": {"task":"compliance.verify_backups","schedule":crontab(minute=0,hour=5,day_of_week=1)},
   }
   celery_app.conf.task_default_queue = "trustshield-default"
   ```

6. ▸ **`config.py`:** add `celery_task_eager: bool = False` (tests run tasks synchronously when True), `celery_deadletter_queue: str = "trustshield-deadletter"`.

7. ▸ **Compose / Helm:** `infra/docker-compose.yml` `worker` service runs `celery -A app.workers.celery_app worker -l info`; add a SEPARATE `scheduler` service running `celery -A app.workers.celery_app beat -l info` (beat must run in exactly one place). Mirror in Helm (two Deployments).

**✓ Verification:**
- `tests/unit/test_celery_beat.py` — assert `celery_app.conf.beat_schedule` has the 7 keys with the expected crontab args.
- `tests/unit/test_tasks_call_services.py` — with `task_always_eager=True`, calling `nightly_usage_rollup.delay()` invokes the wrapped service fn (mock the AsyncSession); on a raised exception, retry count increments and dead-letter path triggers (C2.2).
- Live: `celery -A app.workers.celery_app inspect active` + `inspect scheduled` lists tasks.

---

## C2.2 — Task Idempotency & Dead-Letter

**Files:** modify the four task modules from C2.1; create `backend/app/workers/deadletter.py`; modify `backend/app/services/alerting/alert_service.py`.

**Steps:**

1. ▸ **Dedupe key** — derive per run: `task_id = f"{task_name}:{scheduled_bucket}"` where `scheduled_bucket = datetime.utcnow().strftime("%Y%m%d%H")` for hourly, `"%Y%m%d"` for daily. Each task computes its own bucket.

2. ▸ **Redis SET dedupe** — at task start, `SET NX EX 7200 task_id "running"`; if it returns False (already running/done), exit early with `self.request.chain = None`. On success set value `"done"`; on final failure set `"failed"`.

3. ▸ **Dead-letter path** — wrap each task body in try/except; after `self.request.retries >= max_retries`:
   - `deadletter.publish(task_name, payload, exc, traceback)` → pushes to the `celery_deadletter_queue` (or a Redis list `deadletter:<task>`).
   - `await alert_service.trigger_alert(severity="critical", title=f"Celery task {task_name} dead-lettered", ...)`.

4. ▸ **`alert_service`** — confirm it has a generic `trigger_alert(severity, title, body, runbook_url)`; if not, add it routing to Alertmanager webhook (C4.2) or Slack.

5. ▸ **Expose depth metric** — `deadletter_depth = Gauge("celery_deadletter_depth", "by task", ["task"])`; a 60s Celery beat ticker (or a Prometheus scrape of the Redis list length) updates it.

**✓ Verification:**
- `tests/unit/test_task_idempotency.py::test_double_fire_runs_once` — call `nightly_usage_rollup.delay()` twice in the same bucket, assert the service fn invoked once (mock counter == 1).
- `tests/unit/test_deadletter.py::test_exhausted_retries_alerts` — force the service fn to always raise, run with `max_retries=0`, assert deadletter queue length 1 and `alert_service.trigger_alert` called.
- `tests/unit/test_deadletter.py::test_retries_with_backoff` — assert 3 retries before dead-letter.

---

## C2.3 — Kafka Consumer Hardening (conditional)

**Files:** modify `backend/app/workers/kafka_consumer.py`; gate startup on `settings.event_backend == "kafka"`.

**Steps:**

1. ▸ **Skip-if-redis** — at module top, if `settings.event_backend != "kafka"`, the consumer's `run()` is a no-op with a debug log. Document that the default path is Redis pub/sub and Kafka is opt-in.

2. ▸ **Consumer config** — `enable.auto.commit = False`, `group.id = "trustshield-<concern>"` (one consumer group per concern: analyze, webhook), `max.poll.records = 50`, `session.timeout.ms = 30000`.

3. ▸ **At-least-once + idempotent handler** — each handler dedupes on `event["event_id"]` via a Redis SET (TTL 24h). Commit offset ONLY after handler returns successfully.

4. ▸ **Poison-pill handling** — wrap deserialize in try/except; on `json.JSONDecodeError` or schema violation, publish to `deadletter-topic` and continue (do NOT block the partition). Log + alert.

**✓ Verification:**
- `tests/unit/test_kafka_consumer.py::test_poison_pill_to_deadletter` — mocked consumer yields a bad message; assert it lands in dead-letter and the poll loop continues.
- `tests/unit/test_kafka_consumer.py::test_no_commit_on_handler_crash` — handler raises; assert offset NOT committed (message redelivered on next poll).

---

# Pillar C3 — Model Serving at Scale

## C3.1 — BentoML Model Service

**Files:** create `backend/ml/serving/bentofile.yaml`, `backend/ml/serving/service.py`; modify `backend/requirements.txt`.

**Steps:**

1. ▸ **`requirements.txt`:** add `bentoml>=1.2.0` (consider an extras group `pip install -e ".[serving]"` so the API image stays lean — keep the model-server deps out of the API wheel).

2. ▸ **`bentofile.yaml`:** `service: "service.py:ScamClassifierService"`, `include: ["service.py", "artifacts/"]`, `python.version: "3.11"`, `docker.python_version: "3.11"`.

3. ▸ **`service.py`:**
   - `class ScamClassifierService(bento.Service)` with `__init__` loading the transformer + GBM ONNX from a bundled `artifacts/` dir (or S3 path via env — C3.3) and the calibration.pkl (Phase B B2.2) once at startup.
   - `@bento.api(input=Text(), output=JSON()) def classify_transformer(self, text: str) -> dict:` → run ONNX, apply calibrator, return `{label, confidence}`.
   - `@bento.api def classify_gbm(self, features: dict) -> dict:` → run GBM ONNX.
   - Add `@bento.api def health(self) -> dict:` for readiness.

4. ▸ **Batching** — set `bento.Service` traffic config for dynamic batching (`batching.window=10ms`, `max_batch_size=32`) so the transformer benefits from GPU batching.

**✓ Verification:**
- Local: `cd backend/ml/serving && bentoml serve service.py:ScamClassifierService` → `curl localhost:3000/classify_transformer -d '{"text":"share your otp"}'` returns `{label:..., confidence:...}` in <50ms warm.
- `bentoml build` produces a Bento; `bentoml containerize <name>` produces a runnable image; the image's `/health` returns 200.

---

## C3.2 — Client Migration (API → Model Service)

**Files:** modify `backend/app/services/nlp/model_loader.py`, `backend/app/services/nlp/classifier.py`; modify `backend/app/config.py`.

**Steps:**

1. ▸ **Config (`config.py`):** add `model_service_url: str = ""`, `model_service_timeout_ms: int = 100`.

2. ▸ **`model_loader.py`:**
   - Extract the existing in-process loader into `class OnnxModelLoader` with methods `load()`, `async classify_transformer(text)`, `async classify_gbm(features)`, `calibrator`.
   - Add `class RemoteModelClient` using `httpx.AsyncClient` (base_url = `model_service_url`); methods match the interface. On `httpx.TimeoutException`/5xx, raise a `ModelServiceUnavailable` custom exception.
   - `ModelLoader` factory: `def get_loader(): return RemoteModelClient(...) if settings.model_service_url else OnnxModelLoader()`.

3. ▸ **`classifier.py`** — the tiered fallback (transformer → GBM → keywords, Phase B B2.4) is unchanged in structure. Wrap the transformer call in `asyncio.wait_for(loader.classify_transformer(text), timeout=...)`; on `TimeoutError` or `ModelServiceUnavailable`, fall to GBM; increment `model_fallback_total{tier=...}`. The keyword fallback remains the last resort.

4. ▸ **Keep eager load in lifespan** — Phase B B2.4 added `ModelLoader().load()` in startup; keep it for the in-process path (no-op for remote).

**✓ Verification:**
- `tests/unit/test_model_loader.py::test_empty_url_uses_inprocess` — empty `model_service_url` → `OnnxModelLoader`.
- `tests/unit/test_model_loader.py::test_remote_timeout_falls_through` — mock `httpx` to raise TimeoutException, assert GBM path taken + counter incremented.
- `tests/integration/test_model_service_fallback.py` — spawn BentoML service in a subprocess (test fixture), point classifier at it, assert correct labels; kill the service, assert graceful fallback to in-process GBM.

---

## C3.3 — Model Artifact Store (S3)

**Files:** create `backend/app/services/ml/artifact_store.py`; modify `backend/ml/training/run_pipeline.py`; modify the model registry table usage.

**Steps:**

1. ▸ **`artifact_store.py`:**
   - `class S3ArtifactStore(bucket, client=None)` — `upload(version, local_dir) -> manifest`, `download(version, dest_dir)`, `resolve(version) -> s3_key`, `list_versions() -> list[str]`.
   - Manifest = `{version, git_sha, created_at, files: {name: sha256}, training_metrics}`.

2. ▸ **`run_pipeline.py`** (Phase B B2.1) — after writing local artifacts + `metrics.json`, if `--upload` flag: `artifact_store.upload(version, "ml/artifacts/transformer")`, write the manifest to the `model_params` registry row (the table from Phase B). `git_sha = subprocess.check_output(["git","rev-parse","HEAD"])`.

3. ▸ **Registry as source of truth** — `ModelParams.is_active` (Phase B) points at the active version. Promote/rollback = flip the pointer + the serving service's `artifact_store.download(new_version, cache)`.

4. ▸ **Local cache** — the serving service and in-process loader cache downloaded artifacts to `~/.trustshield/cache/<version>/`; a version is downloaded once per host.

**✓ Verification:**
- `tests/unit/test_artifact_store.py::test_upload_download_roundtrip` — moto S3, upload a temp dir, download to a new dir, assert file contents + manifest sha256 match.
- `test_resolve_returns_key` — after upload, `resolve(version)` returns the S3 key.
- `test_serving_pulls_cached_version` — serving service starts with empty cache, pulls version X, serves; restart uses cache (no S3 GET).

---

# Pillar C4 — Observability & SRE

## C4.1 — Grafana Dashboards

**Files:** create `infra/dashboards/{overview,billing,model,compliance}.json`; `infra/dashboards/dashboards.yml` (Grafana provisioning provider).

**Steps:**

1. ▸ **Confirm emitted metrics first** — `grep -r "Counter\|Gauge\|Histogram" backend/app` to list what's registered in `main.py` lifespan (Phase B added `billing_quota_denied_total`, `model_fallback_total`, `audit_chain_break_total`, `pii_decrypt_total`, `stripe_webhook_total`). Add any missing: `Histogram("http_request_duration_seconds", ..., ["route","method"])`, `Gauge("db_pool_utilization", ...)`, `Gauge("celery_deadletter_depth", ["task"])`.

2. ▸ **`overview.json`** panels (PromQL in each panel's `expr`):
   - Request rate: `rate(http_requests_total[5m])` by route.
   - Latency: `histogram_quantile(0.95, rate(http_request_duration_seconds_bucket[5m]))`.
   - Error rate: `rate(http_requests_total{status=~"5.."}[5m]) / rate(http_requests_total[5m])`.
   - DB pool: `db_pool_utilization`, Redis hit rate, active workers (Celery-exported).
   - Templating: `$environment` (label), `$instance`.

3. ▸ **`billing.json`:** `billing_quota_denied_total` by plan, `stripe_webhook_total` by event_type, meter lag (needs a `billing_meter_lag_seconds` gauge — add it to the rollup task), MRR proxy (count active subs × plan price).

4. ▸ **`model.json`:** `model_fallback_total` by tier (the SLA chart — keyword fallback ~0), model-service RPS + p95 latency, drift PSI from `drift_log` (export via a `/metrics`-facing gauge refreshed by the drift task), shadow agreement rate, promotion events.

5. ▸ **`compliance.json`:** `audit_chain_break_total` (flat line at 0), nightly-job success gauge, backup-audit status, DPDP register age (days since `last_reviewed`).

6. ▸ **Provisioning** — `infra/dashboards/dashboards.yml`: `apiVersion: 1, providers: [{name: trustshield, folder: TrustShield, options: {path: /var/lib/grafana/dashboards}}]`. Mount into the Grafana container (Helm).

**✓ Verification:**
- `python -c "import json; [json.load(open(f'infra/dashboards/{n}.json')) for n in ['overview','billing','model','compliance']]"` — all valid JSON.
- Each panel has a non-empty `expr` referencing an emitted metric name (no orphans).
- Manual: import into a local Grafana + Prometheus, confirm panels render (even with zero data).

---

## C4.2 — Alerting Rules & Routing

**Files:** create `infra/alerts/rules.yml`, `infra/alerts/alertmanager.yml`; modify `backend/app/services/alerting/alert_service.py`.

**Steps:**

1. ▸ **`rules.yml`** — Prometheus rules with severity + runbook annotations:
   - CRITICAL `AuditChainBreak`: `increase(audit_chain_break_total[1h]) > 0`.
   - CRITICAL `ModelKeywordFallbackSpike`: `rate(model_fallback_total{tier="keyword"}[5m]) / rate(model_fallback_total[5m]) > 0.05`.
   - CRITICAL `BillingMeterLagHigh`: `billing_meter_lag_seconds > 3600`.
   - CRITICAL `DriftPSIHigh`: `drift_psi > 0.2` for 30m.
   - CRITICAL `NightlyJobFailed`: `celery_deadletter_depth > 0`.
   - WARNING `DBPoolSaturation`: `avg(db_pool_utilization) > 0.8` for 5m.
   - WARNING `ApiLatencyHigh`: `histogram_quantile(0.95, rate(http_request_duration_seconds_bucket[5m])) > 0.5`.
   - WARNING `StripeWebhookErrors`: `rate(stripe_webhook_total{status=~"4.."}) > 0.05`.
   - Each: `annotations: {runbook: "https://github.com/.../infra/RUNBOOK.md#<alert>"}`.

2. ▸ **`alertmanager.yml`** — `route.receiver: default`; `receivers`: `critical-pagerduty` (PagerDuty routing_key), `ops-slack` (Slack webhook `#trustshield-ops`), `incidents-slack` (`#trustshield-incidents`). Route `severity=critical → critical-pagerduty + incidents-slack`; `severity=warning → ops-slack`. `group_by: [alertname, environment]`, `group_wait: 30s`, `repeat_interval: 4h`.

3. ▸ **`alert_service.py`** — unify on Alertmanager: replace any direct Slack webhook code with a POST to Alertmanager's API (`POST /api/v2/alerts` with a synthesized alert). Keep `trigger_alert(severity, title, body, runbook_url)` signature.

**✓ Verification:**
- `promtool check rules infra/alerts/rules.yml` → exit 0.
- `amtool check-config infra/alerts/alertmanager.yml` → exit 0.
- `tests/unit/test_alert_service.py::test_routes_to_alertmanager` — mock POST, assert payload shape + labels.

---

## C4.3 — Structured Logging & Trace Correlation

**Files:** modify `backend/app/middleware/request_id.py`, `backend/app/main.py` (the `RequestIDFormatter`); add `structlog` config; add OTel spans in hot paths.

**Steps:**

1. ▸ **`requirements.txt`:** add `structlog>=24.0.0`.

2. ▸ **`main.py`** — replace the `RequestIDFormatter` with a structlog JSON processor chain: `structlog.configure(processors=[timestamper, add_log_level, structlog.contextvars.merge_contextvars, structlog.processors.CallsiteParameterAdder, JSONRenderer()])`. Bind `request_id`, `trace_id`, `span_id` into contextvars in `RequestIDMiddleware`.

3. ▸ **Trace injection** — `trace_id = format(trace.get_current_span().get_span_context().trace_id, "032x")`; `span_id` likewise. Bind both in the middleware so every log line in the request carries them. This joins Loki logs ↔ Jaeger traces.

4. ▸ **Explicit spans** (auto-instrumentation covers FastAPI/SQLAlchemy/Redis; add manual spans for the cost-centers):
   - `analyze.py`: wrap the handler body in `with tracer.start_as_current_span("analyze.handle"):`.
   - `classifier.py`: `with tracer.start_as_current_span("classify_transformer"):` around the model call.
   - `pii_vault.py`: `with tracer.start_as_current_span("encrypt_field"):` / `decrypt_field`.
   - `usage_service.py`: `check_quota`, `record_usage`.

5. ▸ **Sentry `before_send`** — in `main.py` Sentry init, add a `before_send` that scrubs PII from breadcrumbs/extras using `app.utils.pii.redact` (Phase B B4.4). This prevents victim PII leaking to Sentry.

**✓ Verification:**
- `tests/unit/test_structlog.py::test_log_has_correlation_ids` — make a request via TestClient, capture the root log handler output, assert JSON has `request_id`, `trace_id`, `span_id`, `endpoint`, `duration_ms`.
- Manual: run locally with OTLP collector + Jaeger + Loki; a `/analyze` request produces a trace with the named child spans and a log line joined by `trace_id`.

---

## C4.4 — SLO Tracking

**Files:** create `infra/dashboards/slo.json`; add recording rules to `infra/alerts/rules.yml`.

**Steps:**

1. ▸ **Recording rules** (append to `rules.yml`):
   - `job:http_availability:ratio_rate30m` = `1 - (sum(rate(http_requests_total{status=~"5.."}[30m])) / sum(rate(http_requests_total[30m])))`.
   - `job:analyze_p95:rate5m` = `histogram_quantile(0.95, rate(http_request_duration_seconds_bucket{route="/api/v1/analyze"}[5m]))`.
   - Burn rate pairs: 1h and 6h windows for each SLO.

2. ▸ **SLOs:** availability 99.9%, analyze p95 < 300ms, webhook p95 < 300ms, audit integrity 100%.

3. ▸ **`slo.json`:** panels for current 30d attainment (%) per SLO + a burn-rate panel (fast-burn pages early). Page when 6h burn > 14.4× (2% budget in 1h).

**✓ Verification:**
- `promtool check rules` passes with the new recording rules.
- `slo.json` validates; each panel references a recording rule name that exists.

---

# Pillar C5 — Client & Mobile Parity

## C5.1 — Consumer PWA (Report + Lookup)

**Files:** create `frontend/app/[locale]/(public)/report/page.tsx`, `frontend/app/[locale]/(public)/check/page.tsx`, `frontend/public/manifest.json`; add `next-pwa` to `frontend`; modify `frontend/lib/api.ts`, `frontend/middleware.ts`.

**Steps:**

1. ▸ **`manifest.json`:** name `TrustShield`, short_name, icons (192/512 maskable), `start_url: "/"`, `display: standalone`, `theme_color`, `background_color`. Add `<link rel="manifest">` in `frontend/app/layout.tsx`.

2. ▸ **`next.config`** — wrap with `withPWA` (dest: "public", register: true, disable in dev). Add `next-pwa` to `package.json`.

3. ▸ **`lib/api.ts`** — add `reportScam(payload)` → `POST /api/v1/report`, `lookupReputation(entityValue, entityType)` → `GET /api/v1/reputation/lookup`. Use the existing `fetch<T>` helper (credentials included).

4. ▸ **`report/page.tsx`** — form: entity_value, entity_type (PHONE|UPI|URL), scam_type (select), description; submit → show reference number + "report another" CTA. Tailwind + the existing form components.

5. ▸ **`check/page.tsx`** — input entity_value + type; submit → reputation badge (green/yellow/red) + report count + last reported date from the reputation response.

6. ▸ **`middleware.ts`** — ensure `report` and `check` are in the public-route allowlist (no auth) and locale-prefixed.

7. ▸ **Rate-limit awareness** — the public routes are behind `rate_limit_scan` (Phase A); on 429, show a friendly "too many checks, try later" message.

**✓ Verification:**
- `npm run build` succeeds; `report` and `check` render under `/en/report`, `/hi/report`, etc.
- Lighthouse PWA audit (mobile) → installable.
- `tests/` (frontend, if present): report submission returns a reference; 429 handled.

---

## C5.2 — i18n Completion

**Files:** the locale catalogs (confirm path: `frontend/messages/` or `frontend/i18n/` — inspect before editing); add `scripts/lint-i18n.mjs`.

**Steps:**

1. ▸ **Inventory** — `grep -rho "t(\"[^\"]*\")" frontend/app frontend/components | sort -u` → the full key set. Compare against each locale's catalog.

2. ▸ **Complete `en`, `hi`, `ta`, `te`** — every key resolves in all four. Prioritize public-facing (report/check/consumer) strings.

3. ▸ **`scripts/lint-i18n.mjs`** — parse all `t("...")` calls + all catalogs; fail if (a) any key used but missing in a locale, or (b) any catalog key unused. Add `"lint:i18n": "node scripts/lint-i18n.mjs"` to `package.json` scripts.

4. ▸ **Add to CI** (X2 below).

**✓ Verification:**
- `npm run lint:i18n` → exit 0, zero missing/unused.
- Native review (manual) of `hi`/`ta`/`te` for naturalness.

---

## C5.3 — Public REST Client Docs

**Files:** create `docs/API_GUIDE.md`, `docs/openapi.yaml`; add a script `scripts/export_openapi.py`.

**Steps:**

1. ▸ **`export_openapi.py`** — `from app.main import app; json.dump(app.openapi(), open("docs/openapi.yaml","w"))` (write JSON, convert to YAML via `pyyaml`). Run on every release; commit the result.

2. ▸ **`docs/API_GUIDE.md`** sections:
   - **Auth** — API key header (`X-API-Key`) for banks, JWT for analysts; how to register a bank and obtain a key.
   - **Pre-transaction webhook** — request schema, response (verdict + risk score + recommended action), the 429 quota response.
   - **Error reference** — 401 (bad key), 403 (wrong role), 422 (validation), 429 (quota, with `Retry-After`), 5xx.
   - **Rate limits per plan** (free/pro/bank/enterprise).
   - **Quickstarts** — curl, Python (`httpx`), Node (`fetch`) — each a complete register→auth→webhook loop.
   - **Webhook signature verification** (if we sign outbound callbacks — document the HMAC scheme).

3. ▸ **Version the guide** with the app version; note deprecations.

**✓ Verification:**
- `swagger-cli validate docs/openapi.yaml` → exit 0.
- The guide's curl example, run against local dev, returns 200 with a verdict.
- Guide covers all four error classes.

---

# Pillar C6 — Scale Verification & Chaos

## C6.1 — Load Profile & Capacity Ceiling

**Files:** modify `backend/tests/load/test_analyze.py` (locust); extend `infra/docker-compose.loadtest.yml`; create `infra/PERFORMANCE.md`.

**Steps:**

1. ▸ **Locust user classes:**
   - `AnalyzeUser` (weight 60): `POST /api/v1/analyze` with text-chat payloads.
   - `WebhookUser` (weight 30): `POST /api/v1/webhook/pre-transaction`.
   - `BatchUser` (weight 10): `POST /api/v1/analyze/batch` (5 sessions each).
   - Each authenticates as a seeded bank (API key).

2. ▸ **Profile mix** — representative payloads seeded in a `fixtures/` dir; randomize per request.

3. ▸ **Target:** spawn to hold 500 RPS sustained (10 min), then burst to 1500 RPS (30s).

4. ▸ **`docker-compose.loadtest.yml`** — bring up the full managed-shape stack (or point at staging): API replicas (3), worker, scheduler, model service, pgbouncer, Postgres, Redis. Locust master + workers.

5. ▸ **Find the bottleneck** — watch the dashboards (C4.1): DB pool saturation? model-service latency? GIL in the in-process fallback? Tune: pool size, HPA, model-service replicas.

6. ▸ **Record** in `PERFORMANCE.md`: max sustained RPS, p50/p95/p99 at 500 RPS, burst p95, per-replica capacity, chosen HPA thresholds (`cpu>70%`, `rps>400/replica`).

**✓ Verification:**
- 10-min run at 500 RPS → p95 < 300ms on `/analyze`, zero 5xx, no SLO burn.
- 30s burst at 1500 RPS → p95 < 800ms, error rate < 0.1%.
- `PERFORMANCE.md` documents numbers + HPA thresholds.

---

## C6.3 — Chaos & DR Drill

**Files:** create `infra/chaos/experiments.md`, `infra/DR_RUNBOOK.md`.

**Steps:**

1. ▸ **Experiment 1 — kill API replica:** `kubectl delete pod -l app=api` mid-traffic. Pass: no 5xx spike, LB drains < 5s.

2. ▸ **Experiment 2 — kill model service:** `kubectl scale deploy/model-service --replicas=0`. Pass: `model_fallback_total{tier="keyword"}` rises, requests still return (degraded), `ModelKeywordFallbackSpike` alert fires.

3. ▸ **Experiment 3 — kill worker:** delete worker pod mid-rollup window. Pass: job resumes on restart, no double-processing (C2.2 dedupe), dead-letter depth 0.

4. ▸ **Experiment 4 — partition Redis:** network policy blocking Redis. Pass: circuit breaker trips, write path degrades gracefully (or fails closed safely), alert fires.

5. ▸ **DR drill:** restore the latest RDS snapshot to a fresh instance; reconfigure the app to point at it; run `audit_service.verify_chain(db)` over the full table. Pass: zero breaks, restore time < 30 min. Record date + outcome in `DR_RUNBOOK.md`.

**✓ Verification:**
- All 4 chaos experiments pass their criteria (recorded in `experiments.md`).
- DR drill: restored DB passes `verify_chain()` with zero breaks; time recorded.

---

## C6.4 — Security Review & Pen-Test Prep

**Files:** create `docs/THREAT_MODEL.md`, `docs/PEN_TEST_SCOPE.md`; review `infra/SECRETS_RUNBOOK.md`, `.gitleaksignore`.

**Steps:**

1. ▸ **`THREAT_MODEL.md`** — STRIDE per trust boundary: public API, bank API (key auth), admin (JWT role), worker, model service, DB, KMS. For each: threats, controls, residual risk.

2. ▸ **`PEN_TEST_SCOPE.md`** — in-scope endpoints + auth mechanisms; out-of-scope (AWS infra); provided test accounts; responsible-disclosure terms.

3. ▸ **CI gates audit** — confirm gitleaks + trivy green (Phase A/B); justify every entry in `.gitleaksignore` or remove it.

4. ▸ **Audit-forgery test** — `tests/unit/test_audit_forgery.py`: tamper a row's payload (not via the service, directly UPDATE), run `verify_chain`, assert it's flagged invalid. Confirms the chain can't be silently forged without the signing key.

**✓ Verification:**
- `THREAT_MODEL.md` covers every boundary.
- `test_audit_forgery.py` passes (tamper detected).
- gitleaks/trivy clean; `.gitleaksignore` justified.

---

# Cross-Cutting

## X1 — Tests

- **Unit (`tests/unit/`):** `test_kms_provider.py`, `test_secrets_loader.py`, `test_database.py`, `test_artifact_store.py`, `test_remote_model_client.py`, `test_model_loader.py`, `test_celery_beat.py`, `test_tasks_call_services.py`, `test_task_idempotency.py`, `test_deadletter.py`, `test_kafka_consumer.py`, `test_structlog.py`, `test_alert_service.py`, `test_audit_forgery.py`.
- **Integration (`tests/integration/`):** `test_kms_roundtrip.py`, `test_model_service_fallback.py` (BentoML subprocess), `test_worker_lifecycle.py` (Celery eager), `test_pii_reencrypt_migration.py`.
- **Load (`tests/load/`):** the C6.1 locust suite.
- **Coverage gate:** raise `pytest --cov-fail-under` from 70 (Phase B) to **75**.

## X2 — CI (`.github/workflows/ci.yml`)

- **`infra-validate`** job: `terraform -chdir=infra/terraform validate` + `terraform plan` (dry/mock backend) on `infra/terraform/**` changes.
- **`migrate-fresh-db`** job: Postgres service container → `alembic upgrade head` → assert exit 0 (real Postgres, not SQLite).
- **`dashboards-validate`** job: JSON-lint `infra/dashboards/*.json`; `promtool check rules infra/alerts/rules.yml`; `amtool check-config infra/alerts/alertmanager.yml`.
- **`i18n-lint`** job in frontend pipeline: `npm run lint:i18n`.
- **Deps:** add `bentoml`, `moto>=5`, `structlog`, `boto3` to `backend/requirements.txt` (moto under a dev/`extras_require` test group).

## X4 — Documentation

- `README.md`: managed-infra quickstart, local model-service run, chaos/DR drill trigger.
- `infra/DEPLOYMENT.md`: full prod env-var list (KMS key id, Secrets Manager prefix, model service URL, S3 artifact bucket), HPA config, pool-sizing rationale.
- New: `infra/PERFORMANCE.md`, `infra/DR_RUNBOOK.md`, `infra/RUNBOOK.md`, `docs/THREAT_MODEL.md`, `docs/PEN_TEST_SCOPE.md`, `docs/API_GUIDE.md`.

---

# Recommended Execution Sequence

```
C1.1 → C1.2 → C1.3 → C1.4          (infra + KMS slice)
‖
C2.1 → C2.2 → C2.3?                 (scheduling slice — wraps existing Phase B fns)
‖
C4.3                                (structured logging — unblocks debugging)
→
C3.1 → C3.2 → C3.3                  (model serving slice)
→
C4.1 → C4.2 → C4.4                  (observability slice — needs all metric sources)
→
C5.1 → C5.2 ‖ C5.3                  (client parity, parallel)
→
C6.1 → C6.3 → C6.4                  (scale/security gate — LAST)
→
X1 / X2 / X4                        (woven throughout, finalized at the end)
```

**Atomicity rule:** each numbered step above is one commit-sized unit. Do not bundle a pillar into a single PR — a reviewer should be able to verify one step at a time.
