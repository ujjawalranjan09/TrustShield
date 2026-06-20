# TrustShield Professional Upgrade — Full Implementation Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** Transform TrustShield from a demo/prototype into a professional-grade fraud detection platform with real ML, proper auth, persistent storage, real-time features, and production-ready infrastructure.

**Architecture:** Phase-based implementation — each phase builds on the previous. Foundation first, then auth, then real data, then ML, then real-time, then testing.

**Tech Stack:** FastAPI, PostgreSQL, Neo4j, Redis, Kafka, Next.js 14, SQLAlchemy (async), Alembic, JWT, ONNX, Celery, WebSocket

---

## Phase 1: Foundation & Infrastructure

### Task 1.1: Consolidate Settings (remove duplicate config)
- **File:** `backend/app/config.py` — rewrite with pydantic_settings.BaseSettings
- **File:** `backend/app/main.py` — remove duplicate Settings class, import from config
- **Verify:** App starts without error

### Task 1.2: Create .env.example
- **File:** `backend/.env.example` — document all env vars with descriptions
- **Verify:** All config.py fields covered

### Task 1.3: Add Request ID Middleware
- **File:** `backend/app/middleware/request_id.py` — new file
- **File:** `backend/app/main.py` — add middleware
- **Verify:** All log lines include request_id

### Task 1.4: Improve Health Check
- **File:** `backend/app/main.py` — health endpoint checks DB, Redis, Neo4j
- **Verify:** `/health` returns dependency statuses

### Task 1.5: Wire Alembic Properly
- **File:** `backend/alembic.ini` — configure
- **File:** `backend/alembic/env.py` — wire to app models
- **File:** `backend/app/main.py` — remove create_all, use alembic
- **Verify:** `alembic upgrade head` creates all tables

### Task 1.6: Add GitHub Actions CI
- **File:** `.github/workflows/ci.yml` — lint, test, build
- **Verify:** Workflow file is valid YAML

### Task 1.7: CORS Production Config
- **File:** `backend/app/config.py` — add production origins
- **Verify:** Config supports comma-separated origins

---

## Phase 2: Authentication & User Management

### Task 2.1: User Model
- **File:** `backend/app/models/user.py` — User model with roles
- **Verify:** Model imports cleanly

### Task 2.2: Auth Service (JWT)
- **File:** `backend/app/services/auth/jwt_service.py` — JWT creation/verification
- **File:** `backend/app/services/auth/__init__.py`
- **Verify:** Unit test for token creation/validation

### Task 2.3: Auth API Endpoints
- **File:** `backend/app/api/v1/auth.py` — register, login, refresh, me
- **File:** `backend/app/main.py` — mount auth router
- **Verify:** POST /api/v1/auth/register and /login work

### Task 2.4: Role-Based Access Control
- **File:** `backend/app/auth.py` — rewrite with JWT + role checking
- **Verify:** Protected endpoints require valid JWT

### Task 2.5: Frontend Auth
- **File:** `frontend/app/login/page.tsx` — login page
- **File:** `frontend/lib/auth.ts` — auth context/hooks
- **File:** `frontend/middleware.ts` — route protection
- **Verify:** Login flow works, dashboard is protected

---

## Phase 3: Persistent Storage (Remove All Mocks)

### Task 3.1: Intel Network → PostgreSQL
- **File:** `backend/app/models/intel.py` — Bank, SharedEntity, CrossBankReport models
- **File:** `backend/app/api/v1/intel.py` — rewrite with DB queries
- **Verify:** Banks persist across restarts

### Task 3.2: Recovery Cases → PostgreSQL
- **File:** `backend/app/models/recovery.py` — RecoveryCase model
- **File:** `backend/app/api/v1/recovery.py` — rewrite with DB queries
- **Verify:** Cases persist across restarts

### Task 3.3: Real Dashboard Stats
- **File:** `backend/app/models/scan_event.py` — ScanEvent model
- **File:** `backend/app/api/v1/analyze.py` — log scan events
- **File:** `backend/app/api/v1/analytics.py` — query real stats
- **Verify:** Dashboard shows real scan counts

### Task 3.4: Real Hotspot Data
- **File:** `backend/app/models/hotspot.py` — add geo fields to reports
- **File:** `backend/app/api/v1/hotspots.py` — query real geo data
- **Verify:** Hotspots reflect actual reported data

### Task 3.5: Wire Neo4j Graph into Analyze Pipeline
- **File:** `backend/app/services/graph/entity_graph.py` — real Neo4j queries
- **File:** `backend/app/api/v1/analyze.py` — call graph service
- **Verify:** Graph enrichment returns real data

### Task 3.6: Audit Trail Table
- **File:** `backend/app/models/audit.py` — AuditLog model
- **File:** `backend/app/middleware/audit.py` — log all mutations
- **Verify:** All POST/PUT/DELETE logged to DB

---

## Phase 4: ML Engine Improvements

### Task 4.1: Feedback Endpoint
- **File:** `backend/app/api/v1/feedback.py` — submit labeled examples
- **File:** `backend/app/models/feedback.py` — FeedbackLabel model
- **Verify:** POST /api/v1/feedback stores labels

### Task 4.2: Model Training Pipeline
- **File:** `backend/ml/training/train.py` — training script with metrics
- **File:** `backend/ml/training/evaluate.py` — evaluation on holdout
- **Verify:** Script runs and outputs metrics

### Task 4.3: Explainability Endpoint
- **File:** `backend/app/api/v1/explain.py` — per-prediction explanations
- **Verify:** Returns contributing keywords and entity weights

### Task 4.4: Batch Analysis API
- **File:** `backend/app/api/v1/batch.py` — bulk analysis endpoint
- **Verify:** Accepts array of sessions, returns array of results

---

## Phase 5: Real-Time Features & Alerting

### Task 5.1: WebSocket for Dashboard
- **File:** `backend/app/api/v1/ws_dashboard.py` — WebSocket endpoint
- **File:** `frontend/components/LiveFraudFeed.tsx` — connect to WS
- **Verify:** Real events appear on dashboard

### Task 5.2: Alerting System
- **File:** `backend/app/services/alerting/alert_service.py` — webhook/email/Slack
- **File:** `backend/app/models/alert.py` — AlertConfig model
- **Verify:** Critical fraud triggers alert

### Task 5.3: PII Handling
- **File:** `backend/app/utils/pii.py` — masking/redaction utilities
- **File:** `backend/app/middleware/pii_logger.py` — mask PII in logs
- **Verify:** VPAs/phones masked in log output

---

## Phase 6: Testing & Quality

### Task 6.1: Unit Tests for All Services
- **File:** `backend/tests/unit/test_classifier.py`
- **File:** `backend/tests/unit/test_entity_extractor.py`
- **File:** `backend/tests/unit/test_risk_scorer.py`
- **File:** `backend/tests/unit/test_action_engine.py`
- **Verify:** All pass

### Task 6.2: Integration Tests (Expanded)
- **File:** `backend/tests/integration/test_auth.py`
- **File:** `backend/tests/integration/test_feedback.py`
- **File:** `backend/tests/integration/test_recovery.py`
- **Verify:** All pass

### Task 6.3: API Contract Tests
- **File:** `backend/tests/contract/test_api_schemas.py`
- **Verify:** All response schemas validate

---

## Execution Order
1. Phase 1 (Foundation) — do first, everything depends on it
2. Phase 2 (Auth) — needed before protected features
3. Phase 3 (Persistence) — remove all mocks
4. Phase 4 (ML) — improve detection engine
5. Phase 5 (Real-time) — add live features
6. Phase 6 (Testing) — validate everything
