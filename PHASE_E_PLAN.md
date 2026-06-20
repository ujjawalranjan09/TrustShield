# TrustShield — Phase E Implementation Plan: Enterprise & Ecosystem

> **Status:** Planning document — NO code in this file. Execution spec for a coding agent.
> **Prerequisite:** Phase D complete (live graph intelligence, grounded explainability LLM, multi-modal ingest, proactive intervention, reputation flywheel). TrustShield now *detects deeply*; Phase E makes it *deployable inside a real bank* and *embedded across the partner ecosystem*. This is the "from product to platform" phase.
> **Goal of Phase E:** Turn a single-tenant SaaS into a multi-tenant enterprise platform: banks bring their own identity (SSO/SAML/OIDC), get fine-grained RBAC + SCIM team provisioning, run in a regional/data-residency cell, integrate via official SDKs + signed webhooks + an embeddable console, and trust a customer-facing SLA backed by formal change management. Six pillars: **E1 Multi-Tenancy & Isolation**, **E2 Enterprise Identity (SSO + SCIM)**, **E3 RBAC & Permissions**, **E4 Ecosystem Integration (SDKs, Webhooks, Embed)**, **E5 Enterprise Governance (SLA, Change Mgmt, Audit)**, **E6 Regional Cells & Data Residency**.
> **Exit gate:** A second bank onboarded into an isolated tenant with SSO login (no TrustShield password), SCIM-provisioned teams + scoped roles, their data invisible to the first bank at every API/DB/log layer, an iOS/Android/Web SDK integration streaming live scans with signed-webhook callbacks, a published 99.9% SLA with change-management evidence, and deployment into an India-only data-residency cell (all victim PII stays in-region per DPDP §16).

---

## 0. How to Read This Plan (for the executing agent)

- **Build order matters.** E1 (tenancy) is the spine — every later pillar is scoped per-tenant. E2/E3 (identity + RBAC) build on E1's tenant model. E4 (ecosystem) exposes the now-tenant-aware platform. E6 (cells) is the deploy topology that enforces E1's isolation at the infra level — it lands last, after the app is tenant-correct, so cell-sharding is a placement decision not a rewrite. E5 (governance) is cross-cutting evidence that ties it together for procurement.
- **Every task has Location, Action, Verification.** Location = exact file(s). Action = prose (NO code). Verification = test/endpoint/contract.
- **Conventions (unchanged):** FastAPI async + SQLAlchemy 2.0, Pydantic v2, Alembic, `app.services.<domain>`, Celery in `app/workers/`. Frontend: Next.js app router, `lib/api.ts`. Infra: managed AWS (Phase C) + Helm. The `Bank` model already exists (`backend/app/models/intel.py`); E1 promotes it to a first-class tenant — do not create a parallel tenant concept.
- **Every new model needs:** env.py import, `init_db()` import, Alembic migration chained off the Phase D head. `alembic upgrade head` clean after each.
- **No default secrets.** New config (`saml_*`, `oidc_*`, `scim_*`, `webhook_signing_secret`) empty-default; `main.py` lifespan startup check rejects empties in non-dev (Phase B/C pattern).
- **Per-task DoD:** migration applies, unit + integration tests pass, `ruff check .` clean, endpoint/contract returns documented result. Tenant-isolation tasks additionally require a **cross-tenant leak test** (tenant A cannot read tenant B's data via any endpoint) — this is the core correctness gate of the phase.

---

## Pillar E1 — Multi-Tenancy & Isolation

**Objective:** Today all data lives in one logical DB with `bank_id` as an optional FK. A bank querying `/analyze` can in principle see another bank's reports through the graph/reputation endpoints. Phase E makes `tenant_id` a **mandatory, enforced** dimension on every row, every query, every log — so isolation is structural, not aspirational.

### E1.1 — Tenant Model & Migration

- **Location:** create `backend/app/models/tenant.py`; modify every domain model that holds tenant data (`scan_event.py`, `session.py`, `intel.py`, `recovery.py`, `feedback.py`, `billing.py`, `behavioral_signals`, `shadow_prediction.py`, `audit.py`, `intervention_logs`); Alembic migration.
- **Action:** Define `Tenant` (`__tablename__="tenants"`): `tenant_id` (String(36) PK, uuid4), `slug` (unique, URL-safe), `display_name`, `tier` ("bank"|"enterprise"|"platform"), `status` ("active"|"suspended"|"offboarding"), `data_region` ("ap-south-1"|"ap-south-2" — E6), `created_at`. A `Tenant` maps 1:1 to a `Bank` for bank tenants (the Bank's `bank_id` becomes the `tenant_id`) and 1:1 to a non-bank enterprise org for others — one tenant concept, two flavors, do not fork. Add a non-null `tenant_id` (String(36), FK → tenants.tenant_id, indexed) to every tenant-scoped model. **Data migration:** backfill `tenant_id` from the existing `bank_id`/`user_id` for every row (every existing row belongs to *some* bank/user; rows with neither — platform data like `Plan` — get a `platform` tenant sentinel). Add a composite unique constraint where business logic needs it (e.g., `(tenant_id, session_id)` on scan_events).
- **Wiring:** add to `env.py` + `init_db()`.
- **Verification:** Migration applies; backfill test (seed pre-migration rows with bank_id/user_id, post-migration all have a tenant_id); composite-constraint test (duplicate `(tenant_id, session_id)` rejected).

### E1.2 — Tenant Context Middleware & Query Enforcement

- **Location:** create `backend/app/middleware/tenant_context.py`; modify `backend/app/auth.py` (resolve tenant from the auth token/API key); modify every DB query site OR — preferred — a **session-scoped query filter**.
- **Action:** `TenantContextMiddleware` resolves `request.state.tenant_id` from the authenticated principal (JWT `sub` → user → tenant; `X-API-Key` → bank → tenant) and stores it in a contextvar (`tenant_context`). The preferred enforcement is a **SQLAlchemy event listener** (`before_compile` / a custom `Query` base) that injects `WHERE tenant_id = :current_tenant` into every SELECT/UPDATE/DELETE on tenant-scoped models — so a developer *cannot* forget the filter. Platform-wide queries (admin cross-tenant dashboards) explicitly opt out via a `bypass_tenant()` context manager (super_admin only, audited). This is the single highest-leverage control in the phase: if it's a manual discipline, it will leak.
- **Verification:** **Cross-tenant leak test** — seed tenant A + B with private data; authenticate as A; hit every read endpoint and assert zero B rows. A test that a raw `db.execute(select(ScanEvent))` without bypass returns only the current tenant's rows. A test that `bypass_tenant()` is logged with the caller's user id.

### E1.3 — Tenant-Aware Audit, Logs, & Metrics

- **Location:** modify `backend/app/services/audit/audit_service.py`, the structlog config (Phase C C4.3), the Prometheus metric labels.
- **Action:** (1) Every audit-log row carries `tenant_id` (it already has actor + action — add the dimension). (2) Structlog binds `tenant_id` into the contextvars alongside `request_id`/`trace_id`, so every log line is tenant-attributable — essential for multi-tenant incident debugging. (3) Add `tenant_id` as a Prometheus label on the key counters (`billing_quota_denied_total`, `model_fallback_total`, `intervention_sent_total`) so the dashboards (Phase C C4.1) can slice by tenant. Guard against high-cardinality blowup (tenant count is bounded, unlike user_id).
- **Verification:** Audit row has tenant_id; a log line from a tenant-A request carries `tenant_id=A`; a dashboard panel grouped by tenant shows per-tenant breakdown.

### E1.4 — Tenant Onboarding & Offboarding

- **Location:** create `backend/app/services/tenant/lifecycle.py`; `backend/app/api/v1/tenant.py` (super_admin only); Celery task.
- **Action:** `provision_tenant(slug, tier, region)` creates the Tenant row, a platform-level subscription (Phase B), a default admin user, and seeds default roles (E3). `offboard_tenant(tenant_id)` is a **governed, reversible** process: mark `status=offboarding`, export all the tenant's data (reuse the Phase B compliance `export_pack` scoped to the tenant — this is the data-portability deliverable), and after a retention hold, hard-delete the tenant's rows in dependency order (respecting RBI 7-year retention for recovery data — offboarding a bank tenant cannot delete recovery cases; document the carve-out). Offboarding is a Celery job with a confirmation step.
- **Verification:** Onboarding test creates a working tenant (login, default roles). Offboarding test: a non-recovery tenant is fully deleted; a bank tenant's recovery rows survive (retention carve-out); the export pack contains all the tenant's data; the process is reversible up to the retention-hold cutoff.

---

## Pillar E2 — Enterprise Identity (SSO + SCIM)

**Objective:** Banks will not create TrustShield-managed passwords for their analysts. They expect to log in via their IdP (Okta/Azure AD/Google) and have their security team provision/deprovision users via SCIM. Today auth is local JWT only. Phase E adds SAML + OIDC inbound SSO and SCIM 2.0 user provisioning.

### E2.1 — SAML 2.0 Inbound SSO

- **Location:** create `backend/app/services/auth/saml_service.py`, `backend/app/api/v1/sso.py`; add deps (`python-saml` or `pyca/pyopenssl`-based — evaluate `python3-saml`); config in `config.py`.
- **Action:** Per-tenant SAML config (stored encrypted, Phase B vault): IdP metadata URL, entity ID, x509 cert, ACS URL. Flow: `GET /auth/saml/login?tenant=<slug>` → redirect to IdP → IdP POSTs SAML assertion to `/auth/saml/acs` → validate signature, extract `nameid` + attributes (email, groups) → map to a local `User` (create on first login via JIT provisioning, E2.3) → issue the TrustShield access/refresh JWT (reuse Phase B `jwt_service`). Just-in-time group → role mapping via E3.2. Store the IdP session index for single-logout.
- **Config:** `saml_sp_entity_id`, `saml_sp_acs_url`, per-tenant IdP config in a `tenant_saml_configs` table (encrypted values).
- **Verification:** Integration test with a mocked IdP (or test-saml-idp container): a signed assertion → JWT issued; a tampered assertion → 401; group claims map to the right roles.

### E2.2 — OIDC Inbound SSO

- **Location:** create `backend/app/services/auth/oidc_service.py`; add to `backend/app/api/v1/sso.py`; deps (`authlib` or `itsdangerous`).
- **Action:** Standard authorization-code flow against an OIDC provider (Azure AD, Google, Okta). Per-tenant config: `client_id`, `client_secret` (encrypted), `discovery_url`. `GET /auth/oidc/login?tenant=<slug>` → redirect → callback `/auth/oidc/callback` → exchange code → validate ID token (signature + `iss`/`aud`/`exp`) → extract `sub`/email/groups → JIT provision → JWT. Prefer OIDC for new tenants (simpler than SAML); keep SAML for legacy enterprise IdPs.
- **Verification:** Integration test with a mocked OIDC provider (or Dex testcontainer): code exchange → JWT; invalid `aud` → 401; group claim → role mapping.

### E2.3 — JIT Provisioning & Account Linking

- **Location:** modify `backend/app/models/user.py`, `backend/app/services/auth/provisioning.py`.
- **Action:** On first SSO login, if no `User` with the IdP-asserted email exists, create one (status `active`, tenant from the SSO config, role from group mapping E3.2) — JIT. **Account linking:** if a user already exists with that email (e.g., a migrated local account), link the SSO identity to it (store `sso_subject` + `idp`) rather than creating a duplicate. Support multiple IdPs per user (an analyst might have Okta for work + Google for personal — both link to one account). Never auto-link by email alone if the email is unverified (IdP-verified is fine; risk: account takeover via unverified email claim).
- **Verification:** First SSO login creates the user; second login authenticates without duplication; linking a second IdP to an existing user works; an unverified-email claim does NOT auto-link (test the takeover guard).

### E2.4 — SCIM 2.0 Provisioning

- **Location:** create `backend/app/api/v1/scim.py` (SCIM endpoints under `/scim/v2/`); deps (optional `scim2-filter-parser` for query support).
- **Action:** Implement the SCIM 2.0 provider subset banks actually use: `GET/POST/PUT/PATCH /scim/v2/Users`, `/scim/v2/Groups`, with pagination (`startIndex`/`count`) and attribute filtering. Auth via a per-tenant SCIM bearer token (issued at tenant onboarding, rotatable). Map SCIM `User` ↔ TrustShield `User`, SCIM `Group` ↔ TrustShield role/team (E3). `PATCH` (op=add/remove/replace on `members` or `groups`) drives real-time role changes — when Okta removes a user from the "Fraud Analysts" group, their TrustShield role revokes within seconds. This is the deprovisioning guarantee (a fired analyst's access dies immediately).
- **Verification:** A SCIM client (or `scim2-tester`) creates/updates/deactivates a user end-to-end; a group-membership PATCH changes the live role; deactivating a user in the IdP invalidates their active sessions (E2.5).

### E2.5 — Session Revocation & Token Family Invalidation

- **Location:** modify `backend/app/services/auth/jwt_service.py` (Phase B), `backend/app/auth.py`; create `backend/app/models/auth.py` (session/revocation table).
- **Action:** Today access tokens are stateless (15min) — fine — but refresh tokens need a **revocation list** for deprovisioning. Store issued refresh-token `jti`s (Phase B already mints them) in a `refresh_token_sessions` table with `status` (active/revoked). SCIM deactivation (E2.4) or an admin "revoke sessions" action marks all of a user's refresh tokens revoked → next refresh fails → they must re-SSO (which will fail if deactivated). Optional: shorten access-token TTL to 5min for tenants that want tighter revocation. Add a `token_version` claim; bumping it on the user revokes all outstanding tokens.
- **Verification:** Revoke-test: a user's refresh fails after revocation; SCIM-deactivate cascades to session invalidation; a `token_version` bump invalidates all access tokens.

---

## Pillar E3 — RBAC & Permissions

**Objective:** Today `require_role(*allowed_roles)` is a flat string check ("analyst"/"super_admin"). Enterprise procurement needs: fine-grained **permissions** (not just roles), per-tenant **custom roles**, and **resource-level** scoping (an analyst sees only their assigned cases). Phase E introduces a permission model without breaking the existing role checks.

### E3.1 — Permission Model

- **Location:** create `backend/app/models/auth.py` (`Permission`, `Role`, `RolePermission`, `UserRole`); modify `backend/app/auth.py`.
- **Action:** Define a permission catalog as code (not data) — `app/services/auth/permissions.py` enumerates the atomic permissions (`scan:read`, `scan:analyze`, `report:create`, `recovery:read`, `recovery:write`, `intervention:send`, `model:promote`, `billing:manage`, `audit:read`, `tenant:admin`, etc.). Roles are tenant-scoped collections of permissions: built-in roles (`tenant_admin`, `analyst`, `viewer`, `compliance_officer`) + tenant-defined custom roles. `User ↔ Role` is per-tenant (a user is an analyst in tenant A, an admin in tenant B — they can hold multiple). Replace `require_role(*roles)` with `require_permission(*perms)` (keep `require_role` as a thin shim that maps role→perms for back-comat). Enforce at the route level AND where a permission implies a data scope (e.g., `recovery:read` implies "only cases assigned to me" unless `recovery:read_all`).
- **Verification:** Permission-catalog test (no orphan permissions); a test that a route guarded by `require_permission("model:promote")` is denied to an analyst and allowed to a tenant_admin; back-comat test that existing `require_role` calls still work.

### E3.2 — Role Mapping from SSO Claims

- **Location:** modify `backend/app/services/auth/provisioning.py`; config per-tenant mapping.
- **Action:** Each tenant configures a mapping from IdP group claims → TrustShield roles: e.g., Okta group `"Fraud-Analysts"` → role `analyst`. Stored in `tenant_saml_configs`/`tenant_oidc_configs`. On each SSO login, re-evaluate the mapping (group membership may have changed) and **reconcile** the user's roles — add new, remove stale. This keeps TrustShield roles a reflection of the IdP source of truth (the bank's security team manages groups in Okta, not in TrustShield).
- **Verification:** Login with group X → role assigned; login again without group X → role removed; a tenant admin's custom mapping is respected.

### E3.3 — Custom Roles UI

- **Location:** create `frontend/app/[locale]/(app)/admin/roles/page.tsx`; `backend/app/api/v1/tenant.py` (role CRUD endpoints).
- **Action:** A tenant-admin UI to create/edit custom roles: name, pick permissions from the catalog (checkboxes grouped by domain), assign users. Live preview of the permission set. Cannot edit built-in roles (read-only) but can clone them. Role changes audit-logged (E5).
- **Verification:** Create a custom role, assign to a user, verify the user gains exactly those permissions; editing a built-in role is blocked; changes appear in the audit log.

---

## Pillar E4 — Ecosystem Integration (SDKs, Webhooks, Embed)

**Objective:** Banks integrate via API today; Phase E makes integration *turnkey*: official SDKs (iOS/Android/Web exist as thin shims — harden + version them), **signed outbound webhooks** (so banks trust our callbacks), and an **embeddable console** (an iframe-able trust console a bank can drop into their internal portal). This is what unblocks the integration team.

### E4.1 — SDK Hardening & Versioning

- **Location:** `sdk/web/src/index.ts` (233 lines), `sdk/ios/Sources/TrustShieldSDK.swift` (257), `sdk/android/TrustShieldSDK/TrustShieldManager.kt` (78) — all exist; harden.
- **Action:** (1) Bring all three to **feature parity** on the unified `Verdict` schema (Phase D D3.1) — analyze (text/voice/image), reputation lookup, report submit. (2) **Typed responses** in each language (TypeScript interfaces, Swift structs, Kotlin data classes) generated from the OpenAPI spec (Phase C C5.3) — set up codegen (`openapi-typescript`, `openapi-generator` for Swift/Kotlin) so the SDKs can't drift from the API. (3) **Retry + backoff + circuit breaker** on transient failures (mobile SDK especially — flaky networks). (4) **PII hygiene**: SDKs must never log raw entity values; add a `redact` mode for debugging. (5) **Semantic versioning** + a CHANGELOG; the SDK publishes to npm/CocoaPods/Maven under `@trustshield/*`. (6) **Offline queue** for the mobile SDKs — a scan made offline is queued and flushed on reconnect (critical for low-connectivity Indian mobile conditions).
- **Verification:** All three SDKs compile against the generated types; a parity test (the same analyze call across all three returns the same typed verdict); a retry test (mocked 503 → retried with backoff); an offline-queue test (enqueue while offline → flushed on reconnect).

### E4.2 — Signed Outbound Webhooks

- **Location:** create `backend/app/services/integration/webhook_dispatcher.py`, `backend/app/api/v1/webhook_subscriptions.py`; model `WebhookSubscription` (per-tenant); config in `config.py`.
- **Action:** Tenants register webhook subscriptions (`url`, `event_types` like `scan.completed`/`intervention.sent`/`ring.detected`, `secret`). On an event, the dispatcher POSTs the payload **HMAC-SHA256 signed** with the subscription secret (`X-TrustShield-Signature: t=<unix>,v1=<hmac>` — Stripe-style) so the bank can verify authenticity and prevent replay (the `t=` + a 5-min tolerance). **Retry policy:** exponential backoff, up to 24h, then disable the subscription (with an alert) — a failing webhook shouldn't silently drop events. **Idempotency:** every event has an `event_id`; the bank dedupes. Dead-letter failures. Outbound webhooks respect tenant isolation (E1) — never cross-tenant. PII in payloads is redactable per-subscription (a bank can opt out of raw entity values).
- **Config:** `webhook_signing_secret` (platform default, per-subscription secret overrides), `webhook_max_retries: int = 8`.
- **Verification:** Signature-verification test (a recipient with the secret validates; a tampered payload fails; an old `t=` is rejected as replay); retry test (failing endpoint → backoff → disable); idempotency test (duplicate event_id ignored by recipient); isolation test (tenant A's events never reach tenant B's subscription).

### E4.3 — Embeddable Trust Console

- **Location:** create `frontend/app/embed/[locale]/console/page.tsx` (iframe-able); `backend/app/api/v1/embed.py` (scoped token issuance).
- **Action:** A bank drops an `<iframe src="https://app.trustshield.../embed/console?token=...">` into their internal portal, giving their analysts the scan/reputation/investigation views without a separate login. The embed token is a short-lived JWT scoped to a tenant + a *restricted permission set* (embed tokens can't do admin actions) issued via an authenticated API call from the bank's backend. The embed route strips the TrustShield chrome (no top nav, no global search across tenants) and is CSP-framing-restricted to the bank's origin (via `Content-Security-Policy: frame-ancestors`). This is the "embedded analytics" pattern banks expect.
- **Verification:** Embed token issuance requires a valid bank credential + returns a scoped JWT; the iframe renders only the tenant's data; a frame-ancestors CSP test (loads from the bank's origin, blocked from an attacker origin); a test that an embed token with a restricted set cannot call `tenant:admin` endpoints.

### E4.4 — Integration Sandbox

- **Location:** create `backend/app/api/v1/sandbox.py`; a sandbox tenant type.
- **Action:** A self-serve sandbox: a bank signs up, gets a sandbox tenant with seeded sample data (scam sessions, a fraud ring, a recovery case) and **synthetic** API keys (clearly marked, rate-limited, never touching prod data). The sandbox runs on the same code path but a separate logical DB/schema or a `is_sandbox=true` row-level flag with a strict write-quota (can't pollute the real graph/reputation). This is how integration teams build and test before going live. Add a "reset sandbox" endpoint.
- **Verification:** Sandbox signup → keys → can hit all read endpoints with seeded data; sandbox writes are quarantined (don't appear in prod reputation); reset clears the sandbox.

---

## Pillar E5 — Enterprise Governance (SLA, Change Mgmt, Audit)

**Objective:** A bank's procurement and risk teams need formal evidence: a published SLA, change-management records, an exportable audit trail covering *who did what across which tenant*, and SOC2/ISO-aligned controls. Phase E produces the artifacts, not just the claims.

### E5.1 — SLA Engine & Reporting

- **Location:** create `backend/app/services/governance/sla.py`; Celery task; `backend/app/api/v1/governance.py`.
- **Action:** Compute per-tenant SLA attainment monthly from the metrics already emitted (Phase C C4.4 SLOs): uptime % (successful requests / total, excluding tenant-caused 4xx), latency p95 vs the tier's promise, audit-chain integrity (any break = SLA breach). Publish a monthly **SLA report** (PDF, reuse Phase B `RBIReportBuilder` pattern) per tenant, available in their console. Track incident windows (a linked `Incident` model with start/end/affected-tenants/root-cause) so the report explains any breach. Credits/breaches computed per the contract.
- **Verification:** A seeded incident reduces a tenant's monthly uptime; the PDF report renders the correct numbers; an audit-chain break flags the month as breached.

### E5.2 — Change Management & Release Notes

- **Location:** create `backend/app/models/governance.py` (`ChangeRecord`); `backend/app/api/v1/governance.py`; modify the deploy pipeline.
- **Action:** Every production deploy records a `ChangeRecord`: version, git SHA, deployer, change summary (auto-extracted from commit messages / a `CHANGES.md`), affected tenants (all or a subset), rollback plan, risk level. Tenant admins can subscribe to change notifications (E4.2 webhooks). Breaking API changes require a deprecation window (≥90 days) tracked in the `ChangeRecord` with a sunset date. This is the evidence bank risk teams demand ("show me your change log for Q2").
- **Verification:** A deploy creates a `ChangeRecord`; a tenant subscribed to changes receives a webhook; a breaking change without a sunset date is blocked by a CI check on the OpenAPI diff.

### E5.3 — Cross-Tenant Audit Trail & DLP

- **Location:** modify `backend/app/services/audit/audit_service.py` (Phase B) — add tenant dimension; create `backend/app/services/governance/dlp.py`.
- **Action:** (1) The audit chain (Phase B hash-chain) already records actor+action+payload-hash; add `tenant_id` and make the per-tenant audit view exportable as a tamper-evident bundle (a filtered `verify_chain` scoped to one tenant). (2) **Data-Loss Prevention**: a DLP scan that runs nightly across tenant boundaries — assert no tenant-A PII appears in tenant-B's rows/logs/exports. This is both a compliance control and the regression test for E1.2's enforcement. (3) Admin (platform) actions that *cross* tenants (a TrustShield super_admin viewing a tenant's data for support) are audited at a higher severity with a reason field.
- **Verification:** Per-tenant audit export verifies clean for that tenant; the DLP scan finds zero cross-tenant leaks on a seeded multi-tenant DB; a cross-tenant admin action is logged at critical severity with a reason.

### E5.4 — Compliance Framework Mapping

- **Location:** create `docs/CONTROL_MATRIX.md`; link existing controls.
- **Action:** A control matrix mapping TrustShield's implemented controls to common frameworks (RBI Cyber Security Framework, DPDP Act §8/§16/§25, SOC2 Trust Services, ISO 27001 Annex A). For each control: what it is, where it's implemented (file/feature ref), the evidence artifact (a log/report/metric), and the last test date. This is the document a bank's auditor works from — it converts the implemented features (Phase B-D) into a procured-product story. Reference the Phase B compliance artifacts (DPDP register, attestation bundle) and Phase C (KMS, DR runbook).
- **Verification:** Every control has an implementation ref that resolves to a real file; the matrix is internally consistent (no control claims an unimplemented feature); a reviewer can trace DPDP §16 (data residency) → E6, §8 (data register) → Phase B B3.2.

---

## Pillar E6 — Regional Cells & Data Residency

**Objective:** DPDP §16 requires sensitive personal data to stay in India (or in countries on the approved list). Banks in different regions may require their own cell. Phase E deploys TrustShield as **regional cells**: a tenant is pinned to a cell at provisioning; that tenant's data never leaves the cell. This is the infra enforcement of E1's logical isolation.

### E6.1 — Cell-Aware Routing & Tenant Pinning

- **Location:** modify `backend/app/config.py` (`cell_region`), `backend/app/main.py` (routing), the load balancer / API gateway config, `infra/helm/`.
- **Action:** Each cell deployment knows its `cell_region` (e.g., `ap-south-1`). At tenant provisioning (E1.4), `tenant.data_region` is set and immutable post-creation. An **edge router** (API gateway / a thin routing service) inspects the tenant (from the API key or a JWT claim) and routes the request to the correct cell — if a request arrives at the wrong cell, it's rejected with a redirect to the right cell's URL (never silently proxied with data crossing cells). Document the cell URL scheme (`ap-south-1.trustshield...` / `ap-south-2.trustshield...`).
- **Config:** `cell_region: str = "ap-south-1"`, `cell_routing_enabled: bool = False` (single-cell deployments ignore routing).
- **Verification:** A tenant pinned to cell B hitting cell A's URL → 3xx redirect to cell B, no data fetched; the redirect carries no PII; a single-cell deployment (routing disabled) works unchanged.

### E6.2 — Cross-Cell Coordination (the things that *must* be global)

- **Location:** design doc `docs/CELL_ARCHITECTURE.md`; modify the reputation/graph federation (D1) minimally.
- **Action:** Most data is cell-local (tenant's scans, cases, graph). A few things are intentionally **global**: the *cross-bank reputation* of a phone/UPI (a scammer hits banks in multiple regions — the reputation should aggregate), and the *platform-level* model artifacts (one trained model, served to all cells). Define the federation contract: reputation lookups fan out to peer cells (read-only, PII-tokenized only — the token is the join key, never raw phone) and aggregate; model artifacts sync from a training cell to serving cells via the Phase C S3 artifact store. Everything else stays cell-local. Document the tradeoff (reputation freshness lag across cells) and the invariant (no raw PII crosses cells — only tokens).
- **Verification:** A reputation lookup in cell A for an entity reported in cell B returns the aggregated score (via tokenized federation); no raw PII appears in the cross-cell request (assert only tokens); a cell-partition test (cut the federation link → cell A returns local-only reputation, degrades gracefully).

### E6.3 — Cell DR & Evacuation

- **Location:** `infra/DR_RUNBOOK.md` (extend Phase C C6.3); a cell-evacuation Celery task.
- **Action:** A regional outage (or a regulatory data-localization change) may require **evacuating** a cell: migrate all tenants in cell A to cell B. This reuses E1.4's tenant export/import at scale: export each tenant's data bundle (Phase B export_pack, tenant-scoped), import into cell B, re-pin the tenant's `data_region`, cut over DNS. Reputations re-converge via E6.2 federation. Document the RTO (target: 4h for a full cell) and the validation (every tenant's audit chain verifies post-import).
- **Verification:** An evacuation test (small tenant set) restores all tenants in the target cell with audit chains intact; DNS cutover is documented; RTO is recorded.

---

## Cross-Cutting Tasks

### X1 — Tests

- **Unit:** `test_tenant_context.py`, `test_query_filter_enforcement.py`, `test_cross_tenant_isolation.py` (the core gate — one test per read endpoint), `test_saml_service.py`, `test_oidc_service.py`, `test_jit_provisioning.py`, `test_scim_endpoints.py`, `test_session_revocation.py`, `test_permissions.py`, `test_role_mapping.py`, `test_webhook_signature.py`, `test_webhook_retry.py`, `test_sla_engine.py`, `test_change_record.py`, `test_dlp_scan.py`, `test_cell_routing.py`, `test_reputation_federation.py`.
- **Integration:** `test_sso_e2e.py` (Dex/test-saml-idp testcontainer → JWT), `test_scim_deprovision.py` (Okta-style PATCH → session killed), `test_embed_console.py` (scoped token + CSP), `test_cell_evacuation.py` (export/import/verify).
- **The gating test for the whole phase:** `test_cross_tenant_isolation.py` parametrized over **every** authenticated read endpoint — a tenant-A token gets zero tenant-B rows. This must be green before any E-pillar ships.

### X2 — CI

- **`iso-isolation`** job: runs the cross-tenant leak suite on every PR touching `backend/app/api/`, `backend/app/models/`, or the query-filter listener.
- **`sso-integration`** job: spins up a Dex OIDC + test-saml-idp container, runs the SSO e2e suite. Gated on auth-path changes.
- **`sdk-parity`** job: generates SDK types from OpenAPI, compiles all three SDKs, runs the parity test matrix. Gated on `sdk/**` or OpenAPI changes.
- **`openapi-breaking-change`** check: `oasdiff` against the committed spec — fails on breaking changes without a sunset `ChangeRecord`.
- **Deps:** `python3-saml`/`xmlsec`, `authlib`, `scim2-filter-parser`, `openapi-typescript`, `openapi-generator`, testcontainers for Dex/SAML.

### X3 — Observability

- Add `tenant_id` label to key metrics (E1.3). New metrics: `sso_login_total{idp,result}`, `scim_request_total{op,result}`, `webhook_dispatch_total{result}`, `webhook_retry_total`, `permission_denied_total{permission}`. Add an `enterprise.json` Grafana dashboard: per-tenant usage, SSO health, webhook delivery, permission denials, SLA attainment by tenant.
- Trace spans: SSO assertion validation, SCIM PATCH handling, webhook dispatch + each retry, cell-federation fan-out.

### X4 — Documentation

- `docs/ENTERPRISE_ONBOARDING.md`: SSO setup (SAML/OIDC), SCIM config for Okta/Azure/Google, role mapping, webhook subscription setup, embed-console integration.
- `docs/CELL_ARCHITECTURE.md` (E6.2): what's cell-local vs global, the federation contract, the no-raw-PII-crosses-cells invariant.
- `docs/CONTROL_MATRIX.md` (E5.4): framework → control → evidence mapping.
- `docs/SDK_INTEGRATION.md`: quickstart for web/iOS/Android, the offline-queue model, signature verification.
- Update `docs/API_GUIDE.md` (Phase C) with tenant headers, the webhook signature scheme, the embed token flow.

---

## Exit Gate Checklist (Phase E)

- [ ] **E1:** Two tenants (A, B) provisioned; the cross-tenant leak suite is green across **every** read endpoint; audit/log/metric lines carry `tenant_id`; a bank tenant can be offboarded with recovery-data retention respected.
- [ ] **E2:** A bank admin logs in via SSO (SAML or OIDC) with no TrustShield password; SCIM provisioning from their IdP creates/reconciles users; deactivating a user in the IdP kills their TrustShield session within the access-token TTL.
- [ ] **E3:** A tenant admin creates a custom role, assigns it, and the user gains exactly those permissions; `require_permission` enforces at the route; SSO group claims map to roles.
- [ ] **E4:** The iOS/Android/Web SDKs (generated from OpenAPI) make a typed analyze call with retry/offline-queue; a signed webhook reaches a subscriber and survives a retry storm; the embed console renders tenant-scoped data behind a frame-ancestors CSP.
- [ ] **E5:** A monthly SLA report PDF generates per tenant; a deploy creates a `ChangeRecord` and notifies subscribed tenants; the DLP scan reports zero cross-tenant leaks; the control matrix traces DPDP §8/§16 to real features.
- [ ] **E6:** A tenant pinned to cell B hitting cell A is redirected (no data fetch); a cross-cell reputation lookup aggregates via tokenized federation with no raw PII crossing cells; an evacuation test restores tenants with audit chains intact.
- [ ] All new migrations apply via `alembic upgrade head` on fresh Postgres (CI `migrate-fresh-db` green).
- [ ] `ruff check .` clean; `npm run lint` clean; pytest ≥75% coverage; the **cross-tenant isolation suite** green (this is non-negotiable); SSO/SCIM/SDK integration jobs green in CI.

---

## Dependency Graph (build order)

```
E1.1 (tenant model + migration) ──→ E1.2 (query enforcement) ──→ E1.3 (audit/log/metric)
                                  ──→ E1.4 (lifecycle)
E1.2 ──┬─→ E2.1 (SAML) / E2.2 (OIDC) ──→ E2.3 (JIT/link) ──→ E2.5 (revocation)
       └─→ E3.1 (permissions) ──→ E3.2 (role mapping from SSO) ──→ E3.3 (custom roles UI)
E2.3 ──→ E2.4 (SCIM) ──→ E2.5
E1.2 ──→ E4.2 (webhooks) ──→ E4.3 (embed)
E4.1 (SDKs) [parallel, needs Phase D verdict schema]
E4.4 (sandbox) [needs E1]
E1.3 ──→ E5.1 (SLA) / E5.3 (DLP)        [E5.3 also regresses E1.2]
E5.2 (change mgmt) [needs OpenAPI from Phase C]
E5.4 (control matrix) [last — references everything]
E1.4 + E6.1 (routing) ──→ E6.2 (federation) ──→ E6.3 (evacuation)
```

**Recommended sequence:** E1.1→E1.2→E1.3 (tenancy spine — the cross-tenant leak suite gates everything) → E3.1 (permissions, unblocks E2/E4 authz) → E2.1/E2.2→E2.3→E2.4→E2.5 (identity slice) ‖ E4.1 (SDKs, parallel) → E3.2→E3.3 (RBAC polish) → E4.2/E4.3/E4.4 (ecosystem slice) → E5.1/E5.2/E5.3 (governance) → E6.1→E6.2→E6.3 (cells, last — placement over a tenant-correct app) → E5.4 (control matrix ties it together) → X1/X2/X3/X4 woven throughout.

**Atomicity rule:** each numbered task is a PR; each sub-step (in the detailed companion) is a commit. The cross-tenant isolation suite is the merge gate for E1 — no E2-E6 work merges until it's green, because building identity/ecosystem on an unisolated base is wasted effort.

**Why this phase, why now:** Phases A-D built a detection product that works *for one tenant*. Phase E is what makes a bank's security, procurement, and integration teams all say yes — isolated tenancy, their identity system, turnkey integration, governed change, and in-region data. It's the difference between a product and a platform a regulated enterprise can adopt.
