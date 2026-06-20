# TrustShield — Phase D Implementation Plan: Intelligence & Detection Depth

> **Status:** Planning document — NO code in this file. Execution spec for a coding agent.
> **Prerequisite:** Phase C complete (managed infra + KMS, scheduled workers, external model service, observability, load-verified scale). The system is production-hardened; Phase D deepens the *product* — the detection intelligence and the surfaces that make victims/banks act on it.
> **Goal of Phase D:** Make TrustShield detect more, earlier, and explain itself better. Move from single-message classification to **cross-session graph intelligence** (fraud rings, money-mule networks), wire the **real LLM** behind the explainability chat, ship the **multi-modal ingest** (voice + image/QR) as first-class paths, and stand up the **proactive alerting** that intervenes before money moves. Five pillars: **D1 Graph Intelligence at Scale**, **D2 Explainability LLM (Real RAG)**, **D3 Multi-Modal Ingest**, **D4 Proactive Intervention & Alerts**, **D5 Trust Network & Reputation Growth**.
> **Exit gate:** A 10-node fraud ring seeded across 50 reports is auto-detected and surfaced within one ingest cycle; the `/explain/chat` endpoint answers a "why was this flagged?" question with grounded LLM text + citations in <2s p95 and zero hallucinated session ids; a voice call and a QR image both flow through the unified detection pipeline with a verdict; a victim linked to a flagged entity receives a WhatsApp intervention before their UPI transaction completes.

---

## 0. How to Read This Plan (for the executing agent)

- **Build order matters.** D1 (graph) is the data spine that D2 (explainability) cites and D4 (intervention) triggers from. D3 (multi-modal) is independent ingest capacity. D5 (reputation network) is the growth loop that *feeds* D1 — do it last so the graph has data to reason over. D1 and D3 can proceed in parallel after a shared "ingest normalizer" lands first (see D1.0).
- **Every task has Location, Action, Verification.** Location = exact file path(s). Action = prose (NO code). Verification = test/endpoint/load number.
- **Conventions (unchanged):** FastAPI async + SQLAlchemy 2.0, Pydantic v2, Alembic, `app.services.<domain>`, `require_role`, `verify_bank_api_key`. Frontend: Next.js app router, `lib/api.ts`, Tailwind. Infra: managed AWS (Phase C) + `infra/helm/trustshield/`. The Neo4j driver is already wired in `backend/app/services/graph/entity_graph.py` (scaffolded, degrades to no-op when unreachable) — D1 hardens it, does not rebuild it.
- **Every new model needs:** env.py import, `init_db()` import, Alembic migration chained off the current Phase C head. `alembic upgrade head` clean after each.
- **No default secrets.** New config (`llm_api_key`, `whatsapp_*`, `deepgram_api_key`) empty-default; `main.py` lifespan startup check rejects empties in non-dev (follow the Phase B/C pattern).
- **Per-task DoD:** migration applies, unit + integration tests pass, `ruff check .` clean, the endpoint/job returns the documented result. LLM tasks additionally require a groundedness test (no fabricated session ids) and a latency budget.

---

## Pillar D1 — Graph Intelligence at Scale

**Objective:** The Neo4j layer exists but is under-fed (writes only on explicit report) and under-read (ring detection runs on demand, not on ingest). Phase D makes the graph a **live** intelligence layer: every analyze/webhook/report updates the graph within the request SLA, fraud-ring detection runs as a scheduled + on-ingest-triggered job, and the graph powers a new investigation UI. Crucially, do **not** move graph writes onto the request critical path — they are fan-out after the verdict.

### D1.0 — Ingest Normalizer (shared foundation)

- **Location:** create `backend/app/services/intel/ingest_normalizer.py`; consumed by D1/D4.
- **Action:** A single `normalize_and_emit(event_type, payload, db)` that takes any incoming signal — an `/analyze` verdict, a `/report` submission, a `/webhook` block, a `/voice` transcript, an `/image` OCR result — and produces a canonical `IntelEvent` (entity_value, entity_type, scam_type, risk, source, session_id, occurred_at, geo if present). It then fans out asynchronously to three sinks via the event bus (Phase A `services/events/publisher.py`): (1) graph writer (D1.1), (2) reputation updater (D5.1), (3) intervention evaluator (D4.1). **This is the chokepoint that ensures the graph is always consistent with verdicts** — today graph updates are scattered and some paths skip them. Every detection endpoint calls `normalize_and_emit` after persisting its own row; the fan-out is fire-and-forget (`asyncio.create_task`) so it never adds request latency.
- **Verification:** Unit test that each of the 5 event types maps to a correctly-shaped `IntelEvent`; a test that the fan-out invokes all three sink publishers exactly once; a test that a sink failure is logged and does not abort the others.

### D1.1 — Graph Writer Hardening

- **Location:** modify `backend/app/services/graph/entity_graph.py`; verify the Neo4j connection uses TLS (Phase C hardening).
- **Action:** The writer is scaffolded (writes entities + relationships). Harden: (1) **idempotent MERGE** writes — re-ingesting the same report must not duplicate nodes/edges (use MERGE on `(entity_type, normalized_value)` and accumulate weights on the edge, not create new edges); (2) **batched writes** — a single fan-out collects events for 250ms and flushes as one transaction (reduce round-trips); (3) **backpressure** — if Neo4j is unreachable, buffer events to a Redis list `graph_backlog` and a worker drains it (the existing graceful-degradation path is kept but now it *recovers*, not just drops); (4) **PII in the graph** — entity nodes store the *tokenized* entity (phone → HMAC token from Phase B `pii_vault.tokenize`), never raw PII, so a Neo4j dump is not a breach. Document this invariant in a test.
- **Migration:** none (graph is in Neo4j, not Postgres). Add a `graph_backlog` Redis key to the documented keyspace.
- **Verification:** Unit test: ingest the same report twice → node count unchanged, edge weight incremented; a test that dropping the Neo4j connection mid-flush buffers to `graph_backlog` and a subsequent drain writes exactly the buffered events; a test asserting raw phone never appears in any Cypher parameter (tokenized only).

### D1.2 — Fraud-Ring Detection Job (scheduled + triggered)

- **Location:** modify `backend/app/services/graph/ring_detection.py` (scaffolded); register as a Celery task in `backend/app/workers/tasks/intel_tasks.py`; trigger on ingest from D1.0.
- **Action:** The ring detector exists. Two modes: (1) **scheduled** — Celery beat every 15 min runs full-graph community detection (Louvain/label-propagation via Neo4j GDS if available, else a pure-Python networkx fallback over a snapshot) and flags communities with > N entities, cross-bank overlap, and elevated mean risk as `FraudRing` records (model exists in Phase B migration `b1c2d3e4f5a6`); (2) **on-ingest-triggered** — when a new report lands, run a *bounded* (2-hop) ring check around just that entity and update the entity's `ring_id` immediately so the reputation lookup (D5) reflects it without waiting 15 min. The scheduled job reconciles/corrects the triggered assignments. Store ring stats (size, total reports, first_seen, last_seen, member_banks) on the ring node.
- **Config:** `ring_min_entities: int = 5`, `ring_min_reports: int = 10`, `ring_detect_interval_minutes: int = 15`.
- **Verification:** Unit test: seed a 10-node ring across 50 reports, run the scheduled job, assert one `FraudRing` with 10 members; a test that on-ingest detection tags a new member of an existing ring within the request's async fan-out; a test that the networkx fallback produces the same rings as a mocked GDS call on a small graph.

### D1.3 — Money-Mule / Risk-Propagation

- **Location:** modify `backend/app/services/graph/risk_propagation.py` (scaffolded).
- **Action:** The risk-propagation scaffold propagates risk along edges. Make it a **belief-propagation-style** pass: an entity's propagated risk = weighted combination of its own reports + neighbors' risk decayed by hop distance and edge weight (recency-weighted). Run as part of the scheduled D1.2 job. Persist `propagated_risk` on each entity (a float 0-1) separate from its `direct_risk`, so the reputation layer can expose both ("this UPI has 0 direct reports but is 2 hops from a confirmed ring with propagated risk 0.7"). Guard against runaway propagation (dampening factor + max 3 hops).
- **Verification:** Unit test with a known small graph: assert propagated risk on a 2-hop node matches a hand-computed value; a test that adding a high-risk neighbor raises a low-risk node's propagated risk; a stability test that propagation converges (no oscillation) over repeated runs.

### D1.4 — Investigation UI Backend

- **Location:** modify `backend/app/api/v1/graph.py` and `backend/app/api/v1/intel.py`; add Pydantic response schemas.
- **Action:** Endpoints to power the investigation UI (D-frontend): (1) `GET /graph/entity/{type}/{value}` → the entity node + 2-hop neighborhood (nodes + edges, capped at 200 nodes for render perf) + ring membership + direct/propagated risk; (2) `GET /graph/rings` → paginated list of active fraud rings with stats; (3) `GET /graph/ring/{id}` → ring members + the shared reports/VPAs tying them; (4) `GET /graph/path?from=X&to=Y` → shortest path between two entities (the "are these two scammers connected?" query). All require `require_role("analyst")`+. Responses must redact raw PII in node labels (show masked phone, full only to `super_admin` — reuse Phase B `pii.mask`).
- **Verification:** Integration test: seeded graph → `GET /graph/entity/...` returns 200 with expected neighborhood shape; `GET /graph/path` returns the correct shortest path; an analyst-role token is required (403 without).

### D1.5 — Investigation UI Frontend

- **Location:** create `frontend/app/[locale]/(app)/investigate/network/page.tsx` (extends the existing `investigate/` routes); add a graph-vis component.
- **Action:** A force-directed graph visualization (use `react-force-graph` or `d3` behind a React wrapper — pick whichever is lighter; avoid a heavy dep). Nodes colored by risk (green→red), edges by weight, ring members highlighted with a halo. Click a node → side panel (D1.4 entity endpoint) with reports, ring membership, masked PII, "expand" to fetch 1 more hop. A rings list view (D1.4 `/graph/rings`) with drill-in. Match the existing `investigate/graph` and `investigate/lookup` styling. Lazy-load the viz library (dynamic import) so it doesn't bloat the dashboard bundle.
- **Verification:** Renders a seeded graph; clicking a node opens the panel; the rings view paginates; Lighthouse perf budget on the investigate route holds (no >500kb JS regression).

---

## Pillar D2 — Explainability LLM (Real RAG)

**Objective:** The explainability chat (`/explain/chat`, `rag_chat.py`) is template-only — it answers "why was this flagged?" with canned strings. Phase D wires a real LLM grounded in retrieved session data so an analyst gets a natural-language, *cited* explanation, without hallucinating session ids or risk factors. Grounding is non-negotiable: the LLM may only state facts present in retrieved context.

### D2.1 — Vector Store for Session Context

- **Location:** create `backend/app/services/explain/vector_store.py`; the `pgvector` dep is already in `requirements.txt` (Phase A) — use it.
- **Action:** Embed the explainable context of each `ScanEvent` (the message text, extracted entities, risk factors, attribution scores) into a `session_embeddings` table (new model: `session_id`, `embedding vector(768)` — pgvector, `content_hash` to avoid re-embedding on unchanged sessions). Embedding model: the same IndicBERT/MuRIL sentence transformer the classifier uses (reuse the loaded model — no extra dep), or a dedicated `sentence-transformers/paraphrase-multilingual-MiniLM` if the classifier's isn't an embedding model. Index with `ivfflat`. A Celery task (D2-trigger) re-embeds new/changed sessions nightly; ingestion can also embed inline (small cost) for fresh-retrieval.
- **Migration:** new table `session_embeddings` with the vector column. Add to env.py + init_db().
- **Config:** `embedding_model: str = ""` (empty = reuse classifier model).
- **Verification:** Unit test: embed two similar sessions + one dissimilar, cosine similarity ranks the similar pair higher; a test that re-embedding an unchanged session (same `content_hash`) is a no-op; the migration applies on Postgres with pgvector enabled.

### D2.2 — Retriever + Grounding

- **Location:** create `backend/app/services/explain/retriever.py`; modify `rag_chat.py`.
- **Action:** `retrieve(question, session_id, db, top_k=5)` → (1) if `session_id` given, fetch that session + its top-k similar sessions by vector cosine; (2) also retrieve the *attribution* rows (risk factors, entity matches) for the focal session — these are the grounded "why"; (3) build a strict context block containing ONLY retrieved facts, each tagged with its source id. The LLM prompt (D2.3) is instructed to answer *only* from the context and to cite source ids; any statement without a citation is forbidden. Return the context + sources so the UI can render citations.
- **Verification:** Unit test: retriever returns the focal session + k neighbors; a test that a non-existent session_id returns an empty context (not an error) so the LLM is forced to say "I don't have that session"; a grounding-guard test (D2.4) that any session id in the answer exists in the retrieved context.

### D2.3 — LLM Service (provider-agnostic)

- **Location:** create `backend/app/services/explain/llm_service.py`; modify `rag_chat.py`; config in `config.py`.
- **Action:** A provider abstraction: `LLMProvider` with `async def complete(system, context, question, max_tokens, temperature) -> str`. Two impls: `OpenRouterProvider` (HTTP to the `llm_provider=openrouter` config, default for cloud) and `LocalLLMProvider` (HTTP to a local vLLM/Ollama endpoint, `llm_provider=local`). The system prompt enforces: answer only from context, cite `[S-1234]` style, if insufficient say so, never invent risk factors. `temperature=0.1`, `max_tokens=512` (explanations are short). Wire `rag_chat.answer_question` to call retriever (D2.2) → llm_service → return `{answer, sources, context_ids}`. Keep the template fallback for when `llm_api_key` is empty (dev) so the endpoint never hard-fails.
- **Config:** `llm_api_key: str = ""`, `llm_provider: str = "openrouter"`, `llm_model: str = "anthropic/claude-3.5-sonnet"` (or chosen), `llm_base_url: str = ""` (for local), `llm_timeout_seconds: int = 10`. Fail-fast in non-dev if `llm_api_key` empty (the feature is advertised).
- **PII:** the question and retrieved context pass through `pii.redact` (Phase B B4.4) BEFORE the LLM call — no victim phone/UPI/email reaches the LLM provider. This is a hard boundary; test it.
- **Verification:** Unit test with a mocked provider: answer cites only present session ids; the template fallback runs when no key; a test that a phone number in the retrieved context is redacted before the provider call (assert the mock received no raw phone).

### D2.4 — Grounding Evaluation Harness

- **Location:** create `backend/tests/evaluation/test_rag_grounding.py`; a small gold Q&A set `backend/ml/data/explain_eval.jsonl`.
- **Action:** A test harness (run in CI, opt-in via env to avoid burning LLM budget on every push) that runs ~20 hand-authored (question, focal_session, expected_source_ids, forbidden_claims) pairs against the live LLM. Assertions: (1) every session id cited in the answer is in `expected_source_ids` or retrieved context (no hallucination); (2) no `forbidden_claims` appear (e.g., "the victim lost ₹5 lakh" when the data has no amount); (3) latency < 2s p95. This is the regression gate for the LLM — model/provider swaps must pass it.
- **Verification:** The harness passes on the committed model; a test that injecting a fabricated session id into a mock LLM answer fails the harness.

---

## Pillar D3 — Multi-Modal Ingest

**Objective:** Voice and image/QR endpoints exist but are bolt-on paths producing a separate verdict shape. Phase D makes them first-class: a voice call and a QR image flow through the *same* detection pipeline (entities → risk score → verdict → graph/reputation fan-out via D1.0), so a scam voice call and a scam chat are scored on the same scale and feed the same intelligence.

### D3.1 — Unified Verdict Schema

- **Location:** modify `backend/app/schemas/analyze.py` (the response schema); create `backend/app/services/intel/verdict.py`.
- **Action:** Define a canonical `Verdict` (Pydantic): `{session_id, is_scam, scam_type, risk_score, risk_level, confidence, recommended_action, entities, modality ("text"|"voice"|"image"), attributions, model_tier}`. All three endpoints (`/analyze`, `/voice/analyze`, `/image/analyze`) return this shape (additive — keep existing fields for back-compat, add the canonical ones). A `build_verdict(...)` helper centralizes construction so the three paths can't drift. This unblocks the ingest normalizer (D1.0) treating them identically.
- **Verification:** Unit test: all three modality paths produce a `Verdict` with the same required fields populated; back-compat test that old clients ignoring new fields still parse the response.

### D3.2 — Voice Ingest (Whisper / Deepgram)

- **Location:** modify `backend/app/api/v1/voice.py`, `backend/app/services/voice/whisper_service.py`; config in `config.py`.
- **Action:** The voice path: upload audio → transcribe (`whisper_service` for `voice_provider=whisper`, a new `deepgram_service.py` for `deepgram`) → run the transcript through the *same* `classifier.classify` + `entity_extractor` + `risk_scorer` as text → build a `Verdict(modality="voice")` → `normalize_and_emit`. **PII:** the transcript may contain spoken OTPs/numbers — redact before any external LLM call and before logging. Audio retention: store only the transcript (configurable to drop audio after transcription, per DPDP minimization). Streaming option: for live-call detection, accept a WebSocket audio stream (extend the Phase B `ws_dashboard` pattern) and emit partial verdicts — defer full streaming to D3-stretch, ship batch first.
- **Config:** `voice_provider: str = "mock"` (Phase A), `whisper_model_size`, `deepgram_api_key`, `voice_retain_audio: bool = False`.
- **Verification:** Integration test: upload a sample scam-call wav → 200 with `modality="voice"` + verdict; a test that audio is dropped when `voice_retain_audio=False`; a redaction test that a spoken digit string is masked in logs.

### D3.3 — Image / QR Ingest

- **Location:** modify `backend/app/api/v1/image_analysis.py` (293 lines — refactor); add a QR/UPI decoder.
- **Action:** The image path: upload image → OCR (existing) + QR decode (re-add `pyzbar`/`Pillow` behind a try/optional-import — Phase A removed them for Windows DLL issues; in the managed Linux container they're fine, gate the import) → extract UPI ids, phone numbers, URLs, suspicious text → score via the unified pipeline → `Verdict(modality="image")` → `normalize_and_emit`. Handle the known scam patterns: fake payment-success screenshots (regex/visual mismatch), malicious QR → UPI id resolution, phishing URLs. The QR-decoded UPI id is an *entity* — it flows into the graph (D1) and reputation (D5) just like a reported phone.
- **Config:** `image_qr_decode_enabled: bool = True`.
- **Verification:** Integration test: upload a QR image encoding a flagged UPI → 200 with the UPI extracted as an entity + verdict; a test that a QR-decode-failure degrades to OCR-only (graceful); a test that the extracted UPI flows to `normalize_and_emit`.

### D3.4 — Multi-Modal Dashboard Surface

- **Location:** modify `frontend/app/[locale]/(app)/scan/page.tsx` (or a new tabbed ingest page); `frontend/lib/api.ts`.
- **Action:** A tabbed "Analyze" surface: Text | Voice | Image tabs, each posting to its endpoint, all rendering the unified `Verdict`. A single verdict card component (reused) shows risk score, scam type, entities (masked), recommended action, and a "Why?" button → `/explain/chat` with the session id. Voice tab: drag-drop audio / record (browser MediaRecorder). Image tab: upload + paste.
- **Verification:** All three tabs render the same verdict card; upload flows hit the right endpoints; the "Why?" deep-links to explainability with the session id.

---

## Pillar D4 — Proactive Intervention & Alerts

**Objective:** Today detection is reactive (a bank calls the API mid-transaction). Phase D adds *proactive* intervention: when a victim-linked entity is flagged, push a WhatsApp/ SMS intervention before money moves, and let analysts trigger manual interventions (freeze recommendations, calls) from the dashboard.

### D4.1 — Intervention Evaluator

- **Location:** modify `backend/app/services/intervention/action_engine.py` (exists); wire to D1.0.
- **Action:** The action engine maps a verdict/risk to a recommended action (Phase A/B). Add an `evaluate_intervention(intel_event, db)` called from D1.0's fan-out that decides whether to *proactively* intervene: if an entity reaches a risk threshold OR joins a fraud ring (D1.2) AND we have a victim contact (consented), enqueue an intervention. Intervention types: `whatsapp_warning`, `sms_warning`, `bank_freeze_request`, `manual_callback`. Persist as `InterventionLog` (model from Phase B migration `e1f2a3b4c5d6`). **Consent gate:** never message a victim without recorded DPDP consent on their record — this is a legal invariant; test it.
- **Config:** `proactive_intervention_enabled: bool = False`, `intervention_risk_threshold: float = 0.8`.
- **Verification:** Unit test: a high-risk event with consent → intervention enqueued; same event without consent → no intervention (and logged); a test that ring membership triggers intervention even at lower direct risk.

### D4.2 — WhatsApp Intervention Channel

- **Location:** modify `backend/app/api/v1/whatsapp.py` (exists) + `backend/app/services/intervention/whatsapp_sender.py` (create); config in `config.py`.
- **Action:** The WhatsApp endpoint today likely receives inbound (consumer reports). Add the *outbound* path: `whatsapp_sender.send(template_message(to, template, params)` using the WhatsApp Business Cloud API (`whatsapp_access_token`, `whatsapp_phone_number_id` from Phase A config). Use an approved template ("Your recent contact may be a scam: {summary}. Do not share OTP/UPI. Report at ..."). The sender is called by the intervention dispatcher (a Celery task draining the intervention queue). Rate-limit outbound (WhatsApp has its own; also self-limit). Log every send to the audit chain.
- **Config:** `whatsapp_outbound_enabled: bool = False`. Fail-fast in non-dev if outbound enabled but creds empty.
- **Verification:** Unit test with a mocked WhatsApp API: a queued intervention → one outbound message with the right template + params; a test that a send failure retries then dead-letters without losing the intervention (persisted); an audit-chain test that the send is recorded.

### D4.3 — Bank Freeze / Hold Workflow

- **Location:** create `backend/app/services/intervention/bank_channel.py`; modify `backend/app/api/v1/banker.py`.
- **Action:** For bank customers (the bank holds the victim's account), a high-risk verdict can trigger a *freeze/hold request* back to the bank's internal system. Define a webhook contract: TrustShield POSTs `{case_id, victim_entity, risk, recommended_action: "hold", ttl_seconds}` to a bank-configured callback URL (`bank_freeze_webhook_url` set at bank registration). The bank acknowledges. This is the "intervene before money moves" loop. The banker dashboard (D4.4) shows pending holds. **Idempotent:** key off case_id; a bank dedupes. Never auto-freeze without a bank-side confirmation (we *recommend*, the bank *acts*).
- **Config:** per-bank `freeze_webhook_url` on the `Bank` model (Phase A) — nullable.
- **Verification:** Integration test: a bank with a freeze URL + high-risk verdict → one POST to the (mocked) bank endpoint with the right shape; a test that a missing/empty webhook URL degrades to a dashboard-only alert (no error).

### D4.4 — Intervention Dashboard

- **Location:** create `frontend/app/[locale]/(app)/intervention/page.tsx` (or extend admin); `frontend/lib/api.ts`.
- **Action:** An analyst dashboard of `InterventionLog` rows: filter by type/status/date, click to see the triggering verdict + entity graph snippet (reuse D1.5 panel), buttons to manually trigger an intervention (send WhatsApp, request callback) or mark resolved. Real-time updates via the WebSocket (Phase B `ws_dashboard`). Role-gated to analyst+.
- **Verification:** Renders the queue; manual trigger hits the right endpoint; WS updates push new rows without reload.

---

## Pillar D5 — Trust Network & Reputation Growth

**Objective:** The reputation lookup (`/reputation/lookup`) exists but is thin. Phase D makes reputation a *growing* asset: every report enriches it, fraud-ring membership and propagated risk (D1) feed it, and a public trust-badge widget lets any consumer check an entity — which *feeds* the network (data flywheel).

### D5.1 — Reputation Service Enrichment

- **Location:** modify `backend/app/api/v1/reputation.py` + create `backend/app/services/intel/reputation_service.py`; consumed by D1.0.
- **Action:** `compute_reputation(entity, db)` assembles a score from: direct report count + recency decay, scam-type distribution, fraud-ring membership (D1.2) and propagated risk (D1.3), cross-bank corroboration (reported by N distinct banks = stronger signal than N reports from one bank), and a *time-decayed* weighted sum. Cache the score on the entity row (recompute on each ingest via D1.0). The `/reputation/lookup` endpoint returns `{entity, reputation_tier (clean|watch|suspicious|confirmed_scam), score, direct_reports, propagated_risk, ring_membership, last_reported_at, first_seen}`. Public vs authenticated responses differ (authenticated banks get full detail; public gets tier + count buckets only).
- **Verification:** Unit test: reputation rises with more recent reports, decays with age; ring membership bumps the tier; cross-bank corroboration weights higher than single-bank; the public response omits the detailed fields.

### D5.2 — Public Trust-Badge Widget

- **Location:** create `frontend/app/[locale]/(public)/check/widget/[entity]/page.tsx` (embeddable); `frontend/app/api/lookup/route.ts` (a thin proxy to the backend).
- **Action:** An embeddable trust badge (an `<iframe>`-able route or a script tag) that any third-party site can drop in to show a reputation chip for a phone/UPI. Hits the public reputation endpoint (rate-limited, cached at the edge). Visual: green check / yellow watch / red warning + report count. This is the data-acquisition flywheel — every embed is a check that, if the entity is unknown, prompts "report it here" → feeds D1.
- **Verification:** Renders the badge for known/unknown entities; the public endpoint returns only tier + count; an unknown entity shows "no reports yet — be the first to report" CTA.

### D5.3 — Reputation Refresh & Decay Job

- **Location:** create `backend/app/workers/tasks/reputation_tasks.py` (Celery beat).
- **Action:** Nightly job recomputes reputation for all entities with activity in the last 30 days (recency-weighted decay means stale entities trend toward `clean` unless re-reported). Also recomputes propagated risk (D1.3) on the same cadence. This keeps the reputation from going stale and ensures a rehabilitated entity (no new reports for 6mo) returns to a neutral tier.
- **Config:** `reputation_decay_days: int = 180` (after this with no new reports, trend to clean).
- **Verification:** Unit test: an entity with old reports only → tier trends to clean after the decay window; a re-reported entity resets the decay; the job is idempotent (re-run same night = same scores).

---

## Cross-Cutting Tasks

### X1 — Tests

- **Unit:** `test_ingest_normalizer.py`, `test_graph_writer_idempotent.py`, `test_graph_backlog_recovery.py`, `test_ring_detection.py`, `test_risk_propagation.py`, `test_retriever.py`, `test_llm_service.py`, `test_rag_grounding.py`, `test_verdict_schema.py`, `test_voice_redact.py`, `test_qr_decode.py`, `test_intervention_evaluator.py`, `test_consent_gate.py`, `test_whatsapp_sender.py`, `test_reputation_service.py`, `test_reputation_decay.py`.
- **Integration:** `test_graph_lifecycle.py` (real Neo4j testcontainer), `test_explain_chat_grounded.py` (mocked LLM, real retriever), `test_multimodal_ingest.py` (text+voice+image → same verdict shape), `test_intervention_e2e.py` (verdict → consent → WhatsApp mock → audit).
- **Evaluation:** the D2.4 grounding harness (opt-in CI).
- **Coverage gate:** hold at ≥75 (Phase C level); the LLM grounding harness is a *correctness* gate, not coverage.

### X2 — CI (`.github/workflows/ci.yml`)

- **`graph-test`** job: Neo4j testcontainer service, run `tests/integration/test_graph_lifecycle.py`. Gated on `backend/app/services/graph/**` or `backend/app/api/v1/graph.py` changes.
- **`rag-grounding`** job: the D2.4 harness, runs only when `secrets.LLM_API_KEY` is available (nightly schedule + on `backend/app/services/explain/**` PRs with a `[run-rag]` label) to avoid burning budget per push.
- **`neo4j-validate`** is not needed (no schema migrations), but add a **cypher-lint** check on any committed `.cyp` query files.
- **Deps:** `sentence-transformers` (if not already), `neo4j` (present), WhatsApp/Deepgram SDKs (or `httpx` direct), `pyzbar`/`Pillow` under a Linux-only install. Add a testcontainer for Neo4j (`pip install testcontainers[neo4j]`).

### X3 — Observability

- New metrics: `graph_write_total{result}`, `graph_backlog_depth`, `ring_detected_total`, `llm_call_total{provider,result}`, `llm_latency_seconds` (histogram), `rag_grounding_violations_total`, `intervention_enqueued_total{type}`, `intervention_sent_total{type,result}`, `reputation_lookup_total{tier}`. Register in `main.py` lifespan; add panels to the `model.json` and a new `intelligence.json` dashboard.
- Trace spans: `normalize_and_emit` fan-out, each graph Cypher write batch, `retrieve`, `llm.complete`, `whatsapp.send`.

### X4 — Documentation

- `docs/INTELLIGENCE.md`: how the graph is fed, ring-detection cadence, reputation scoring formula (with the weights), decay policy.
- `docs/EXPLAINABILITY.md`: the grounding contract (LLM may only cite retrieved context), how to swap providers, the evaluation harness.
- `docs/INTERVENTION.md`: the consent model, the bank-freeze webhook contract, message templates.
- Update `docs/API_GUIDE.md` (Phase C) with the unified verdict schema, the new graph endpoints, the reputation badge embed.

---

## Exit Gate Checklist (Phase D)

- [ ] **D1:** Seeding a 10-node ring across 50 reports → auto-detected `FraudRing` within one ingest cycle; 2-hop neighborhood renders in the investigation UI; raw PII never enters Neo4j (tokenized).
- [ ] **D2:** `/explain/chat` answers "why was session S-1234 flagged?" with grounded LLM text + `[S-1234]`-style citations in <2s p95; the grounding harness passes (zero hallucinated session ids / forbidden claims); no raw PII reaches the LLM provider.
- [ ] **D3:** A voice call and a QR image both produce a `Verdict` of the unified schema and flow to the graph/reputation via `normalize_and_emit`; the dashboard renders all three modalities in one verdict card.
- [ ] **D4:** A high-risk event for a consented victim → WhatsApp intervention enqueued + sent (mocked in test); a bank with a freeze webhook receives a hold request; the intervention dashboard shows the queue and supports manual triggers.
- [ ] **D5:** `/reputation/lookup` returns a tier enriched with ring membership + propagated risk; an entity with no reports for `reputation_decay_days` trends to clean; the public trust-badge widget renders and prompts reporting for unknown entities.
- [ ] All new migrations apply via `alembic upgrade head` on fresh Postgres (CI `migrate-fresh-db` green, Phase C).
- [ ] `ruff check .` clean; `npm run lint` clean; pytest ≥75% coverage; the grounding harness green; Neo4j integration test green in CI.

---

## Dependency Graph (build order)

```
D1.0 (ingest normalizer) ──┬─→ D1.1 (graph writer)
                           ├─→ D1.2 (ring detection) ──→ D1.3 (risk propagation)
                           └─→ D5.1 (reputation) ──→ D5.3 (decay job)
D1.1/D1.2/D1.3 ──→ D1.4 (graph API) ──→ D1.5 (investigation UI)

D2.1 (vector store) ──→ D2.2 (retriever) ──→ D2.3 (LLM svc) ──→ D2.4 (grounding harness)

D3.1 (verdict schema) ──┬─→ D3.2 (voice)
                         └─→ D3.3 (image) ──→ D3.4 (dashboard)
                         (both call D1.0 to fan out)

D1.0 ──→ D4.1 (intervention evaluator) ──┬─→ D4.2 (whatsapp)
                                          ├─→ D4.3 (bank freeze)
                                          └─→ D4.4 (dashboard)

D5.1 ──→ D5.2 (badge widget)
```

**Recommended sequence:** D3.1 (unified verdict, unblocks everything) → D1.0 (normalizer, the spine) → D1.1+D1.2+D1.3 (graph intelligence, parallel) → D2.1→D2.2→D2.3→D2.4 (explainability slice) ‖ D3.2+D3.3+D3.4 (multi-modal, parallel) → D5.1 (reputation, needs D1.3) → D4.1→D4.2/D4.3/D4.4 (intervention, needs D1+D5) → D5.2+D5.3 (growth loop, last) → X1/X2/X3/X4 woven throughout.

**Atomicity rule:** each numbered task is a PR-sized unit; each `▸`-equivalent sub-step (in the detailed companion) is a commit. A pillar is never one PR.
