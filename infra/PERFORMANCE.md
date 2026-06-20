# TrustShield Performance & Scale Verification

## Load Test Profile (Locust)

| Endpoint | Weight | RPS Target (500) | RPS Target (1500) |
|----------|--------|-------------------|--------------------|
| `POST /api/v1/analyze` | 60% | 300 | 900 |
| `POST /api/v1/webhook/stripe` | 30% | 150 | 450 |
| `POST /api/v1/batch` | 10% | 50 | 150 |

### Locust Configuration

```python
from locust import HttpUser, task, between

class TrustShieldUser(HttpUser):
    wait_time = between(0.1, 0.5)
    weight = 1

    @task(60)
    def analyze(self):
        self.client.post("/api/v1/analyze", json={...})

    @task(30)
    def stripe_webhook(self):
        self.client.post("/api/v1/webhook/stripe", headers={...}, json={...})

    @task(10)
    def batch(self):
        self.client.post("/api/v1/batch", json={...})
```

## Targets

| Metric | Sustained (500 RPS) | Burst (1500 RPS) |
|--------|---------------------|-------------------|
| p50 latency | < 100ms | < 300ms |
| p95 latency | < 300ms | < 800ms |
| p99 latency | < 500ms | < 1500ms |
| Error rate | < 0.1% | < 1.0% |
| Availability | 99.95% | 99.5% |

### Burst Profile
- Ramp: 0 → 1500 RPS over 60s
- Hold: 1500 RPS for 5 minutes
- Ramp-down: 1500 → 0 over 60s
- Recovery: 2 minutes cooldown before next burst

## HPA Configuration

```yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
spec:
  minReplicas: 2
  maxReplicas: 10
  metrics:
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: 70
    - type: Pods
      pods:
        metric:
          name: http_requests_per_second
        target:
          type: AverageValue
          averageValue: "400"
  behavior:
    scaleUp:
      stabilizationWindowSeconds: 30
      policies:
        - type: Pods
          value: 2
          periodSeconds: 60
    scaleDown:
      stabilizationWindowSeconds: 300
      policies:
        - type: Percent
          value: 10
          periodSeconds: 120
```

## Capacity Ceiling Per Replica

| Resource | Limit | Per-Replica Capacity |
|----------|-------|---------------------|
| CPU | 1000m | ~250 RPS (analyze-weighted) |
| Memory | 512Mi | ~100 concurrent connections |
| DB pool (via PgBouncer) | 20 connections | ~200 RPS per pool |
| Redis connections | 50 | ~500 RPS |
| Kafka consumers | 4 partitions | ~200 RPS ingest |

### Scaling Formula

```
replicas_needed = ceil(target_RPS / RPS_per_replica)
                = ceil(500 / 250) = 2 (sustained)
                = ceil(1500 / 250) = 6 (burst)
```

### Per-Replica Breakdown

| Component | CPU Request | CPU Limit | Memory Request | Memory Limit |
|-----------|-------------|-----------|----------------|--------------|
| API server | 250m | 1000m | 256Mi | 512Mi |
| Worker | 250m | 500m | 256Mi | 512Mi |
| PgBouncer | 50m | 200m | 64Mi | 128Mi |

## SLO Definitions

| SLO | Target | Measurement Window |
|-----|--------|-------------------|
| Availability | 99.95% | 30-day rolling |
| Analyze p95 | < 300ms @ 500 RPS | Per-test run |
| Batch throughput | > 50 jobs/sec | 5-minute sustained |
| Audit chain latency | < 50ms append | Per-request |
| Model inference | < 100ms (local), < 500ms (remote) | Per-request |

## Runbook: Load Test Execution

1. Deploy load test stack: `docker-compose -f infra/docker-compose.loadtest.yml up -d`
2. Start Locust web UI: `http://localhost:8089`
3. Configure 500 RPS sustained:
   - Users: 250, Spawn rate: 50/s
4. Monitor Grafana dashboard for latency/error metrics
5. After sustained test, run burst:
   - Users: 750, Spawn rate: 100/s
6. Capture results and compare against targets
7. Tear down: `docker-compose -f infra/docker-compose.loadtest.yml down`
