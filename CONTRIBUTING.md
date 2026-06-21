# Contributing to TrustShield

Thank you for your interest in contributing to TrustShield! This document provides guidelines and instructions for contributing.

## Code of Conduct

Be respectful, inclusive, and constructive. We are building technology to protect vulnerable users from financial fraud.

## Getting Started

### Prerequisites

- Python 3.11+
- Node.js 18+
- Docker & Docker Compose
- Git

### Development Setup

```bash
# Clone the repository
git clone https://github.com/ujjawalranjan09/TrustShield.git
cd TrustShield

# Start the development stack
make dev

# Or set up manually:
# Backend
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Frontend
cd frontend
npm install
npm run dev
```

## Development Workflow

### 1. Create a Branch

```bash
git checkout -b feature/your-feature-name
```

Use descriptive branch names:
- `feature/add-new-endpoint`
- `fix/auth-token-expiry`
- `docs/update-api-guide`
- `test/add-integration-tests`

### 2. Make Changes

- Follow existing code patterns and conventions
- Write tests for new functionality
- Update documentation if needed

### 3. Commit

Write clear, concise commit messages:

```bash
git commit -m "feat: add rate limiting to scan endpoint"
git commit -m "fix: resolve token refresh race condition"
git commit -m "docs: update API guide with new endpoints"
```

### 4. Push and Create PR

```bash
git push origin feature/your-feature-name
```

Then create a Pull Request on GitHub.

## Code Standards

### Python (Backend)

- **Formatter:** Ruff (configured in `pyproject.toml`)
- **Type hints:** Required for all function signatures
- **Docstrings:** Required for public functions and classes
- **Imports:** Sorted by isort conventions

```bash
# Lint
ruff check backend/

# Format
ruff format backend/
```

### TypeScript (Frontend)

- **Formatter:** Prettier
- **Linter:** ESLint
- **Types:** Strict TypeScript

```bash
# Lint
cd frontend && npm run lint

# Format
cd frontend && npx prettier --write .
```

### Commit Messages

Follow [Conventional Commits](https://www.conventionalcommits.org/):

- `feat:` — New feature
- `fix:` — Bug fix
- `docs:` — Documentation
- `test:` — Adding tests
- `refactor:` — Code refactoring
- `chore:` — Maintenance tasks

## Testing

### Backend Tests

```bash
cd backend

# Unit tests
pytest tests/unit/ -v

# Integration tests
pytest tests/integration/ -v

# All tests
pytest tests/ -v
```

### Frontend Tests

```bash
cd frontend

# Unit tests
npm run test

# E2E tests
npm run test:e2e
```

### Before Submitting a PR

1. Run all tests: `make test`
2. Run linters: `ruff check backend/ && cd frontend && npm run lint`
3. Ensure no type errors
4. Update documentation if adding new features

## Pull Request Guidelines

### PR Title

Use conventional commit format:
```
feat: add new fraud detection endpoint
fix: resolve authentication timeout issue
docs: update deployment guide
```

### PR Description

Include:
- **What** changes were made
- **Why** the changes are needed
- **How** to test the changes
- **Screenshots** if UI changes

### PR Checklist

- [ ] Code follows project conventions
- [ ] Tests added for new functionality
- [ ] All existing tests pass
- [ ] Documentation updated (if applicable)
- [ ] No secrets or credentials committed
- [ ] PR title follows conventional commits

## Reporting Issues

### Bug Reports

Include:
- Steps to reproduce
- Expected behavior
- Actual behavior
- Environment (OS, Python version, Node version)
- Screenshots (if applicable)

### Feature Requests

Include:
- Use case description
- Proposed solution
- Alternatives considered

## Security

If you discover a security vulnerability, please report it responsibly:

1. **Do NOT** open a public GitHub issue
2. Email security@trustshield.io with details
3. Allow time for a fix before public disclosure

See [SECURITY.md](SECURITY.md) for more information.

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
