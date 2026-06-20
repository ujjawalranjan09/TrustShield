# Intelligence Graph

How TrustShield's entity graph is built, enriched, and queried.

## Graph Population (D1.0 Normalizer)

The ingest normalizer (`app/services/intel/ingest_normalizer.py`) processes incoming reports from all modalities (text, voice, image) and extracts entities (phone numbers, VPA addresses, bank accounts, device IDs). Each entity is upserted into the Neo4j graph via `FraudEntityGraph.add_entity()`.

**Entity node properties:**
- `value` — tokenized/hashed entity identifier (PII never stored raw in graph)
- `entity_type` — phone, upi, bank_account, device_id
- `report_count` — cumulative report count (incremented on MERGE)
- `graph_risk_score` — current risk score from propagation
- `pagerank_score` — Personalized PageRank score
- `ring_id` — assigned fraud ring identifier (if any)
- `first_seen` / `last_seen` — timestamps
- `last_risk_update` — last propagation timestamp

**Relationships:**
- `APPEARED_WITH` — links two entities seen in the same session, with `session_id` and `weight` properties.

## Ring Detection

**Cadence:** Runs every 15 minutes via Celery beat (`detect_fraud_rings_task`), and also triggers on-ingest when entity count crosses the minimum threshold.

**Algorithm:**
1. Fetch all entities and edges from Neo4j
2. Build a networkx graph (falls back to simple connected-component clustering if networkx unavailable)
3. Run Louvain community detection
4. Filter communities: minimum 5 entities, minimum 50% report density
5. Assign `ring_id` to member entities in Neo4j
6. Persist `FraudRing` records to PostgreSQL
7. Auto-file `InvestigationCase` for critical rings (≥50 reports, ≥10 entities)

**Risk level assignment:**
| Reports | Entities | Level |
|---------|----------|-------|
| ≥ 50 | ≥ 10 | critical |
| ≥ 20 | any | high |
| ≥ 5 | any | medium |
| < 5 | any | low |

## Reputation Scoring Formula

The reputation score (0–100) combines four components:

```
score = base_score + ring_bump + propagated_component + cross_bank_bump
```

| Component | Formula | Cap |
|-----------|---------|-----|
| base_score | `min(50, log(1 + report_count) * 10) * recency_weight` | 50 |
| ring_bump | 25 if confirmed ring, 15 if any ring | 25 |
| propagated_component | `propagated_risk * 30` | 30 |
| cross_bank_bump | `min(20, banks_reporting * 5)` | 20 |

**Recency weight** (based on `last_seen`):
| Days since last report | Weight |
|------------------------|--------|
| ≤ 7 | 1.0 |
| ≤ 30 | 0.7 |
| ≤ 90 | 0.4 |
| ≤ 180 | 0.2 |
| > 180 | 0.1 |

**Reputation tiers:**
| Score Range | Tier |
|-------------|------|
| ≥ 80 | confirmed_scam |
| ≥ 50 | suspicious |
| ≥ 20 | watch |
| < 20 | clean |

## Belief Propagation

Risk propagation uses a BFS-based belief propagation algorithm (`propagate_belief` in `app/services/graph/risk_propagation.py`).

**Algorithm:**
1. Identify seed entities (report_count ≥ 5)
2. BFS from target entity up to `max_hops` (default 3)
3. Each seed reached at hop *h* contributes `dampening^h * edge_weight`
4. Total risk is clamped to [0, 1]

**Parameters:**
- `dampening`: 0.7 (risk decays 30% per hop)
- `max_hops`: 3 (risk from entities >3 hops away is ignored)
- `edge_weight`: 0.5 (uniform for APPEARED_WITH relationships)

Personalized PageRank runs every 6 hours (`propagate_risk_scores` Celery task) with damping factor 0.85 and 20 iterations.

## Decay Policy

Entity risk scores and reputation scores decay over time through the recency weight mechanism. After 180 days without a new report, the recency weight drops to 0.1, effectively suppressing old entities. The `last_seen` timestamp is updated on each new report, resetting the decay window.

Graph nodes are not deleted — they remain for audit trails but their risk contribution diminishes to near-zero.
