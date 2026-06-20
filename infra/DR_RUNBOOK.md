# TrustShield Disaster Recovery Runbook

**Recovery Time Target (RTO):** < 30 minutes
**Recovery Point Objective (RPO):** < 5 minutes

---

## Pre-Recovery Checklist

- [ ] Incident declared in PagerDuty
- [ ] Slack #trustshield-incidents channel created
- [ ] On-call engineer confirmed
- [ ] Current RDS snapshot time identified
- [ ] Last known good state confirmed

## Step 1: Assess Damage (T+0 to T+5 min)

```bash
# Check RDS instance status
aws rds describe-db-instances \
  --db-instance-identifier trustshield-prod \
  --query 'DBInstances[0].DBInstanceStatus'

# Check EKS cluster health
kubectl get nodes
kubectl get pods -A | grep -v Running

# Check Redis status
redis-cli -h <redis-endpoint> ping

# Check audit chain integrity
curl -s https://api.trustshield.example.com/api/v1/audit/health | jq .
```

- [ ] Determine scope: full outage vs partial
- [ ] Determine cause: infrastructure vs application
- [ ] Communicate status in Slack

## Step 2: RDS Snapshot Restore (T+5 to T+15 min)

```bash
# 1. Identify latest automated snapshot
aws rds describe-db-snapshots \
  --db-instance-identifier trustshield-prod \
  --query 'reverse(sort_by(DBSnapshots, &SnapshotCreateTime))[:3].{ID:DBSnapshotIdentifier,Time:SnapshotCreateTime,Size:AllocatedStorage}' \
  --output table

# 2. Create manual snapshot for safety
aws rds create-db-snapshot \
  --db-instance-identifier trustshield-prod \
  --db-snapshot-identifier trustshield-pre-dr-$(date +%Y%m%d%H%M)

# 3. Restore to new instance
aws rds restore-db-instance-to-point-in-time \
  --source-db-instance-identifier trustshield-prod \
  --target-db-instance-identifier trustshield-dr-restore \
  --restore-time $(date -u -d '5 minutes ago' +%Y-%m-%dT%H:%M:%SZ) \
  --db-instance-class db.r6g.large \
  --multi-az

# 4. Wait for restore to complete
aws rds wait db-instance-available \
  --db-instance-identifier trustshield-dr-restore

# 5. Verify connectivity
psql -h trustshield-dr-restore.xxxxx.ap-south-1.rds.amazonaws.com \
  -U trustshield_user -d trustshield \
  -c "SELECT count(*) FROM audit_logs;"
```

- [ ] Snapshot restore initiated
- [ ] New instance available
- [ ] Database connectivity verified
- [ ] Row counts match pre-incident baseline

## Step 3: Audit Chain Verification (T+15 to T+20 min)

```bash
# 1. Verify chain hash continuity
psql -h trustshield-dr-restore -U trustshield_user -d trustshield -c "
  SELECT id, chain_hash, created_at
  FROM audit_logs
  ORDER BY id DESC
  LIMIT 20;
"

# 2. Check for chain breaks
psql -h trustshield-dr-restore -U trustshield_user -d trustshield -c "
  WITH chained AS (
    SELECT id, chain_hash,
           LAG(chain_hash) OVER (ORDER BY id) as prev_hash
    FROM audit_logs
  )
  SELECT count(*) as breaks
  FROM chained
  WHERE prev_hash IS NOT NULL
    AND chain_hash != sha256((prev_hash || id::text)::bytea);
"

# 3. Verify last 5 minutes of entries exist
psql -h trustshield-dr-restore -U trustshield_user -d trustshield -c "
  SELECT count(*), min(created_at), max(created_at)
  FROM audit_logs
  WHERE created_at > now() - interval '10 minutes';
"
```

- [ ] Chain hash continuity verified (0 breaks)
- [ ] Recent audit entries present
- [ ] No orphaned entries

## Step 4: Redirect Traffic (T+20 to T+25 min)

```bash
# 1. Update application DATABASE_URL to restored instance
# (via AWS Secrets Manager or Doppler)
aws secretsmanager update-secret \
  --secret-id trustshield/prod/database-url \
  --secret-string "postgresql+asyncpg://user:pass@trustshield-dr-restore.xxxxx.ap-south-1.rds.amazonaws.com:5432/trustshield"

# 2. Restart API pods to pick up new connection string
kubectl rollout restart deployment trustshield-api

# 3. Verify API health
curl -s https://api.trustshield.example.com/health | jq .

# 4. Run smoke tests
python backend/tests/smoke/test_critical_paths.py --host=https://api.trustshield.example.com
```

- [ ] DATABASE_URL updated
- [ ] API pods restarted
- [ ] Health check returns 200
- [ ] Smoke tests pass

## Step 5: Validate & Monitor (T+25 to T+30 min)

```bash
# 1. Check error rates
# Grafana: API 5xx rate should drop to < 0.1%

# 2. Check audit chain
curl -s https://api.trustshield.example.com/api/v1/audit/health | jq .

# 3. Check billing meter lag
# Grafana: billing_meter_lag_seconds should return to 0

# 4. Check Celery workers
kubectl logs -l app=trustshield-worker --tail=50 | grep -i "error\|fail"
```

- [ ] Error rate < 0.1%
- [ ] Audit chain healthy
- [ ] Billing meter lag resolved
- [ ] No worker errors in logs

## Step 6: Post-Recovery

- [ ] Declare incident resolved in PagerDuty
- [ ] Post incident report within 24 hours
- [ ] Update DR_RUNBOOK.md if gaps found
- [ ] Schedule next DR drill

---

## Quick Reference: DR Contacts

| Role | Name | Contact |
|------|------|---------|
| On-call Engineer | - | PagerDuty |
| DBA | - | Slack #trustshield-infra |
| Security Lead | - | Slack #trustshield-security |
| Incident Commander | - | Slack #trustshield-incidents |

## Cell Evacuation Procedure

**RTO target:** 4 hours for full cell evacuation

Use this procedure to evacuate all tenants from one regional cell to another (e.g., region decommission, DR migration).

### Prerequisites

- Target cell is deployed and healthy
- `CELL_URLS` env var includes both source and target regions
- Target cell has sufficient capacity for all source tenants

### Evacuation Steps

```bash
# 1. Identify tenants in source region
psql -h <source-db> -U trustshield_user -d trustshield -c "
  SELECT tenant_id, slug, display_name, tier
  FROM tenants
  WHERE data_region = 'ap-south-1';
"

# 2. Run evacuation (via API or script)
# The evacuate_cell() function handles:
#   - Export each tenant's data via compliance export_pack
#   - Import to target cell via /api/v1/compliance/import-pack
#   - Re-pin tenant.data_region to target region
python -c "
import asyncio
from app.services.tenant.evacuation import evacuate_cell
from app.database import AsyncSessionLocal

async def run():
    async with AsyncSessionLocal() as db:
        result = await evacuate_cell('ap-south-1', 'us-east-1', db)
        print(result)

asyncio.run(run())
"

# 3. Verify migration
psql -h <target-db> -U trustshield_user -d trustshield -c "
  SELECT count(*) FROM tenants WHERE data_region = 'us-east-1';
"

# 4. Disable cell routing for source cell (now empty)
# Update CELL_ROUTING_ENABLED=false on source cell

# 5. Monitor target cell for errors
curl -s https://us-east-1.trustshield.io/health | jq .
```

### Evacuation Rollback

If evacuation fails mid-way:
1. Source cell still has data (export is read-only)
2. Failed tenants retain `data_region` pointing to source
3. Re-run evacuation for failed tenants only
4. Source cell remains operational until all tenants migrated

### Evacuation Validation Checklist

- [ ] All tenants in source region count = 0
- [ ] All tenants in target region count matches
- [ ] Audit chain intact on target cell
- [ ] Federation health check shows all peers healthy
- [ ] Smoke tests pass on target cell
- [ ] Source cell decommissioned after 7-day hold period

---

## Quick Reference: Endpoints

| Service | Endpoint | Notes |
|---------|----------|-------|
| RDS Primary | trustshield-prod.xxxxx.ap-south-1.rds.amazonaws.com | - |
| RDS DR | trustshield-dr-restore.xxxxx.ap-south-1.rds.amazonaws.com | Created during DR |
| Redis | rediss://<endpoint>:6380 | TLS required |
| API | https://api.trustshield.example.com | Health: /health |
| Audit Health | https://api.trustshield.example.com/api/v1/audit/health | Chain check |
