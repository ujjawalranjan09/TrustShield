# TrustShield Chaos Engineering Experiments

## Experiment 1: Kill API Replica Mid-Traffic

### Hypothesis
Killing one API replica under sustained traffic causes < 30s of degraded latency and zero data loss.

### Setup
- Deploy API with `replicaCount: 4`
- Start Locust at 400 RPS sustained (100 RPS per replica)
- Grafana dashboard open: API latency, error rate, pod restarts
- Kubernetes context: `kubectl config use-context trustshield-prod`

### Execution
```bash
# Identify a replica pod
kubectl get pods -l app=trustshield-api -o wide

# Kill the pod
kubectl delete pod <api-pod-name> --grace-period=0

# Monitor for 2 minutes
watch kubectl get pods -l app=trustshield-api
```

### Pass Criteria
- [ ] No 5xx errors to clients (ALB reroutes within 10s)
- [ ] Pod restarts within 30s
- [ ] p95 latency stays < 500ms during recovery
- [ ] No dropped audit log entries
- [ ] Audit chain integrity verified post-recovery
- [ ] HPA scales back to 4 replicas within 5 minutes

### Rollback
None needed — Kubernetes self-heals. Verify pod count returns to 4.

---

## Experiment 2: Kill Model Service

### Hypothesis
When the ML model service is unavailable, the system falls back to keyword-based scoring with < 5% increase in false positive rate.

### Setup
- Model service deployed as separate pod or sidecar
- Baseline: 100 analyze requests, record model vs keyword fallback rates
- Monitoring: `model_fallback_total` Prometheus counter

### Execution
```bash
# Identify model service pod
kubectl get pods -l app=trustshield-model -o wide

# Scale to 0
kubectl scale deployment trustshield-model --replicas=0

# Send 100 analyze requests via Locust (10 RPS)
# Observe fallback behavior for 5 minutes

# Restore
kubectl scale deployment trustshield-model --replicas=1
```

### Pass Criteria
- [ ] All analyze requests return a result (no 503s)
- [ ] `model_fallback_total{tier="keyword"}` increases (not flatlines)
- [ ] Keyword fallback produces < 5% false positive rate vs model baseline
- [ ] `ModelKeywordFallbackSpike` alert does NOT fire (threshold: 5% of total calls)
- [ ] No data loss — all audit entries persisted
- [ ] Model service recovers within 60s of scale-up

### Rollback
Scale model deployment back to 1 replica.

---

## Experiment 3: Kill Worker Mid-Rollup

### Hypothesis
Killing a Celery worker during a billing rollup job causes the job to be retried and completed without data loss or double-counting.

### Setup
- Trigger a rollup job: `POST /api/v1/billing/rollup` (or via Celery beat)
- Monitor: `celery_deadletter_depth`, rollup job logs
- Identify the worker processing the rollup: `celery -A app.workers.celery_app inspect active`

### Execution
```bash
# Start rollup job
curl -X POST http://localhost:8000/api/v1/billing/rollup \
  -H "Authorization: Bearer <token>"

# Identify active worker
kubectl logs -l app=trustshield-worker --tail=20 | grep rollup

# Kill the worker pod mid-job
kubectl delete pod <worker-pod-name> --grace-period=0

# Wait for restart and job completion
# Check dead-letter queue depth
```

### Pass Criteria
- [ ] Rollup job completes (check billing_meter_lag_seconds returns to 0)
- [ ] `celery_deadletter_depth` remains 0 (job retried, not dead-lettered)
- [ ] Idempotency key prevents double-counting (`idempotency.py` logic)
- [ ] Audit chain for billing entries is unbroken
- [ ] Worker pod restarts within 30s
- [ ] No billing meter lag spike > 3600s (would trigger alert)

### Rollback
None needed — worker self-heals. Verify job completed and no dead-letter items.

---

## Experiment 4: Partition Redis

### Hypothesis
Redis partition (network isolation) degrades event delivery but does not cause data loss; the system falls back to synchronous processing or retries until Redis recovers.

### Setup
- Redis deployed as single instance (dev/staging) or Sentinel cluster (prod)
- Baseline: 200 events/sec via Kafka consumer
- Monitoring: Redis connection errors, Kafka consumer lag

### Execution
```bash
# Simulate partition using iptables (run on Redis node or use tc)
# Option A: Kubernetes network policy
cat <<EOF | kubectl apply -f -
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: deny-redis
spec:
  podSelector:
    matchLabels:
      app: redis
  ingress:
    - from: []
  policyTypes:
    - Ingress
EOF

# Option B: tc on Redis pod (requires NET_ADMIN)
kubectl exec -it <redis-pod> -- tc qdisc add dev eth0 root netem delay 1000ms loss 100%

# Sustain for 2 minutes, observe behavior

# Restore
kubectl delete networkpolicy deny-redis
# or
kubectl exec -it <redis-pod> -- tc qdisc del dev eth0 root
```

### Pass Criteria
- [ ] API requests still succeed (event_backend="redis" degrades, not fails)
- [ ] Kafka consumer lag increases but does not exceed retention window
- [ ] Audit log entries are buffered (not dropped) during partition
- [ ] No `AuditChainBreak` alert fires
- [ ] On recovery, all buffered events are processed (no data loss)
- [ ] Redis reconnection within 10s of partition removal
- [ ] Connection pool saturates gracefully (no connection leak)

### Rollback
Remove network policy / tc rule. Redis reconnects automatically.

---

## Experiment Schedule

| Experiment | Frequency | Environment | Last Run | Next Run |
|------------|-----------|-------------|----------|----------|
| Kill API Replica | Monthly | Staging | - | - |
| Kill Model Service | Monthly | Staging | - | - |
| Kill Worker Mid-Rollup | Monthly | Staging | - | - |
| Partition Redis | Quarterly | Staging | - | - |

## Prerequisites

- Kubernetes cluster with TrustShield deployed
- Locust load test stack running
- Grafana/Prometheus monitoring active
- PagerDuty alerts silenced during experiment window
- All team members notified via Slack #trustshield-incidents
