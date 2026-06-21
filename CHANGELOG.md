# Changelog

All notable changes to TrustShield will be documented in this file.

Format based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [Unreleased]

### Added
- Comprehensive README with architecture diagram and API examples
- CONTRIBUTING.md with development guidelines
- SECURITY.md with vulnerability reporting policy
- .gitignore updated to exclude debug scripts and internal docs

### Fixed
- Token refresh broken due to `family` → `family_id` claim name mismatch in `auth.py:193`
- Post-logout tokens still valid due to missing `jti` claim in access tokens (`jwt_service.py`)
- Reputation widget route ordering — `/widget` and `/public` routes unreachable due to greedy `{vpa:path}` catch-all (`reputation.py`)
- Missing `WebhookSubscription` and `ChangeRecord` models in `init_db()` causing 500 errors on webhooks/governance endpoints
- Missing `Role`, `UserRole`, `DataAsset` model registration in `init_db()`

### Changed
- Backend endpoints `/recovery/initiate` and `/report` now return HTTP 201 status code
- Logout endpoint enhanced to accept Bearer header in addition to cookies
- Removed 34 irrelevant files from repository (debug scripts, test results, planning docs)
- Repository cleaned and professionalized for open-source

### Removed
- Root-level debug scripts (`check_db.py`, `test_*.py`, etc.)
- Internal test results and planning documents
- Generated artifacts (`rbi_report_mock.pdf`, `trustshield.db.bak`)
- AI coding tool directories (`.hermes/`, `.mimocode/`)

## [1.0.0] - 2026-06-19

### Added
- Initial release of TrustShield fraud detection platform
- FastAPI backend with 32 API routers and 93 endpoints
- Next.js 15 frontend with i18n support (EN/HI/TA/TE)
- NLP pipeline with keyword classifier fallback
- Graph-based entity analysis with Neo4j
- Intervention engine with bilingual warnings
- Recovery workflow with 1930 cybercrime submission
- Compliance reporting (RBI quarterly reports, DPDP data register)
- Multi-tenancy with tenant isolation
- Billing integration with Stripe
- Client SDKs (Web/Android/iOS)
- Docker Compose development stack
- Kubernetes Helm chart for production
- CI/CD pipeline with 13 GitHub Actions jobs
