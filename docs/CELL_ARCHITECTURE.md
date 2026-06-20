# TrustShield Cell Architecture

## Overview

TrustShield supports multi-region deployment via **cells** — isolated regional deployments that maintain data residency compliance (DPDP, RBI mandates). Each cell operates independently with its own database, Redis, and application stack.

## Cell-Local vs Global

| Scope | Cell-Local | Global (Federated) |
|-------|-----------|-------------------|
| Tenant data | All PII, scan events, reports, recovery cases | — |
| User accounts | Per-tenant users, roles, permissions | — |
| Audit logs | Local audit chain per cell | — |
| Reputation scores | Local entity reputation | Aggregated cross-cell reputation (tokenized) |
| Fraud rings | Local ring detection | — |
| Billing | Per-tenant subscriptions | — |
| Graph data | Local fraud entity graph | — |

## Federation Contract

Cross-cell communication follows strict rules:

1. **Tokenized entities only**: Entity values are tokenized via HMAC-SHA256 (`pii_vault.tokenize`) before any cross-cell request. Raw PII never leaves the cell.
2. **Read-only queries**: Federation only supports reputation lookups. No writes cross cell boundaries.
3. **No-raw-PII-crosses-cells invariant**: The middleware and federation layer enforce that no plaintext phone numbers, UPI IDs, email addresses, or other PII is transmitted between cells.
4. **Graceful degradation**: If a peer cell is unreachable, the local cell returns local-only reputation. Federation failures never block user requests.

## Cell Routing

When `CELL_ROUTING_ENABLED=true`, the `CellRoutingMiddleware` intercepts requests:

1. Resolves the requesting tenant's `data_region` from JWT/API key.
2. If the tenant's region differs from this cell's region, returns a `307 Temporary Redirect` to the correct cell URL.
3. The redirect URL contains only the cell URL + original path — no PII in the redirect.
4. Health, metrics, and embed endpoints bypass routing.

Configuration (environment variables):
```
CELL_REGION=ap-south-1
CELL_ROUTING_ENABLED=true
CELL_URLS={"ap-south-1": "https://ap-south-1.trustshield.io", "us-east-1": "https://us-east-1.trustshield.io"}
```

## Cell Evacuation

Cell evacuation migrates all tenants from one region to another (e.g., for DR or region decommission).

- **RTO target**: 4 hours for full cell evacuation
- **Process**: Export via compliance export_pack → Import to target cell → Re-pin `data_region`
- **Rollback**: Keep source cell data until target cell is verified

## Degradation Behavior

| Scenario | Behavior |
|----------|----------|
| Peer cell unreachable | Local-only reputation returned, `federation.peer_count=0` |
| Peer cell returns error | That peer excluded from aggregation |
| No CELL_URLS configured | Federation skipped, local-only mode |
| CELL_ROUTING_ENABLED=false | Single-cell mode, all requests pass through |

## Security Invariants

- Entity values are tokenized before leaving the cell (HMAC-SHA256)
- Redirect responses carry no PII — only the target cell URL
- Federation requests are signed with `X-Federation-Request: true` header
- All inter-cell communication uses TLS (HTTPS)
- No raw PII crosses cell boundaries — enforced at middleware and service layers
