# TrustShield Backup & Restore Runbook

## Backup Strategy

| Component | Backup Method | Retention | RPO | RTO |
|-----------|--------------|-----------|-----|-----|
| Postgres | Automated daily + PITR | 35 days | 5 min | 1 hour |
| Neo4j | Daily dump | 30 days | 24 hours | 4 hours |
| Redis | RDB snapshots | 7 days | 5 min | 30 min |

## Postgres Backup (Managed RDS/Aurora)

### Automated Backups
- **Daily snapshots** at 02:00 IST
- **PITR** (Point-in-Time Recovery) enabled with 35-day retention
- **Cross-region复制** to secondary region (optional)

### Manual Backup
```bash
# AWS RDS
aws rds create-db-snapshot \
  --db-instance-identifier trustshield-prod \
  --db-snapshot-identifier trustshield-manual-$(date +%Y%m%d)

# Verify snapshot
aws rds describe-db-snapshots --db-snapshot-identifier trustshield-manual-20260619
```

### Restore Procedure
```bash
# 1. Stop application writes (or use read replica for restore)
# 2. Restore to point-in-time
aws rds restore-db-instance-to-point-in-time \
  --source-db-instance-identifier trustshield-prod \
  --target-db-instance-identifier trustshield-restore \
  --restore-time "2026-06-19T14:30:00Z"

# 3. Wait for restore to complete
aws rds wait db-instance-available \
  --db-instance-identifier trustshield-restore

# 4. Verify data
psql -h trustshield-restore.xxxxx.ap-south-1.rds.amazonaws.com -U trustshield_user -d trustshield

# 5. Swap DNS to restored instance (if needed)
# 6. Monitor for 24 hours before decommissioning original
```

## Neo4j Backup

### Daily Dump
```bash
# Backup
neo4j-admin database dump neo4j --to-path=/backups/neo4j-$(date +%Y%m%d).dump

# Restore
neo4j-admin database load neo4j --from-path=/backups/neo4j-20260619.dump --overwrite-destination
```

## Restore Drill (Quarterly)

Execute quarterly to validate RTO:

1. **Schedule**: First Monday of each quarter, 02:00 IST
2. **Procedure**:
   - Restore Postgres to point-in-time (2 hours ago)
   - Verify data integrity (row counts, recent transactions)
   - Document actual RTO
   - Decommission restore instance
3. **Success Criteria**:
   - RTO < 1 hour
   - No data loss beyond RPO (5 min)
   - All tables accessible
   - Application connects successfully

## Monitoring

- **CloudWatch alarm** on backup failures
- **PagerDuty alert** if daily backup misses
- **Weekly verification** of backup integrity (automated)
