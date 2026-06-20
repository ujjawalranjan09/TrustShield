# TrustShield Secrets Runbook

## Expected Secret Names

Secrets are stored in AWS Secrets Manager (or Doppler) under the path `trustshield/<env>/<secret>`, where `<env>` is one of `dev`, `staging`, or `prod`.

| Secret Path | Description |
|---|---|
| `trustshield/<env>/db` | PostgreSQL connection credentials |
| `trustshield/<env>/redis` | Redis connection credentials |
| `trustshield/<env>/app` | Application-level secrets (JWT, API keys, etc.) |

## Key Mapping

### `trustshield/<env>/db`

| Key | Description | Example |
|---|---|---|
| `host` | PostgreSQL hostname | `postgres.trustshield.internal` |
| `port` | PostgreSQL port | `5432` |
| `username` | Database user | `trustshield_user` |
| `password` | Database password | *(generated)* |
| `dbname` | Database name | `trustshield` |
| `ssl_mode` | SSL mode for connections | `require` |
| `url` | Full connection string (composite) | `postgresql://user:pass@host:5432/db?sslmode=require` |

### `trustshield/<env>/redis`

| Key | Description | Example |
|---|---|---|
| `host` | Redis hostname | `redis.trustshield.internal` |
| `port` | Redis port | `6379` |
| `password` | Redis AUTH password | *(generated)* |
| `tls` | Enable TLS | `true` |
| `url` | Full connection string | `rediss://:pass@host:6379/0` |

### `trustshield/<env>/app`

| Key | Description | Example |
|---|---|---|
| `JWT_SECRET` | Signing key for JWT tokens | `openssl rand -hex 32` |
| `NEO4J_PASSWORD` | Neo4j auth password | *(generated)* |
| `TRUSTSHIELD_API_KEY` | Internal service-to-service key | *(generated)* |
| `MINIO_ROOT_USER` | MinIO / S3-compatible access key | `admin` |
| `MINIO_ROOT_PASSWORD` | MinIO / S3-compatible secret key | *(generated)* |

## Rotation Procedure

Rotate all secrets every 90 days. Use the quarterly rotation schedule.

### 1. Database Password (`trustshield/<env>/db`)

```bash
# 1. Connect to Postgres
psql -U postgres -h $DB_HOST

# 2. Rotate password
ALTER USER trustshield_user WITH PASSWORD 'new_secure_password';

# 3. Update secret in Secrets Manager
aws secretsmanager update-secret \
  --secret-id trustshield/prod/db \
  --secret-string '{"host":"...","port":5432,"username":"trustshield_user","password":"NEW_PASSWORD","dbname":"trustshield","ssl_mode":"require","url":"postgresql://trustshield_user:NEW_PASSWORD@..."}'

# 4. Rolling-restart pods to pick up new credentials
kubectl rollout restart deployment/trustshield-api -n trustshield
```

### 2. Redis Password (`trustshield/<env>/redis`)

```bash
# 1. Connect to Redis
redis-cli -h $REDIS_HOST

# 2. Set new password
CONFIG SET requirepass "new_secure_password"

# 3. Update secret in Secrets Manager
aws secretsmanager update-secret \
  --secret-id trustshield/prod/redis \
  --secret-string '{"host":"...","port":6379,"password":"NEW_PASSWORD","tls":true,"url":"rediss://:NEW_PASSWORD@...:6379/0"}'

# 4. Rolling-restart
kubectl rollout restart deployment/trustshield-api -n trustshield
kubectl rollout restart deployment/trustshield-worker -n trustshield
```

### 3. Application Secrets (`trustshield/<env>/app`)

```bash
# 1. Generate new values
NEW_JWT=$(openssl rand -hex 32)
NEW_API_KEY=$(openssl rand -hex 32)

# 2. Update secret in Secrets Manager
aws secretsmanager update-secret \
  --secret-id trustshield/prod/app \
  --secret-string "{\"JWT_SECRET\":\"$NEW_JWT\",\"NEO4J_PASSWORD\":\"...\",\"TRUSTSHIELD_API_KEY\":\"$NEW_API_KEY\",\"MINIO_ROOT_USER\":\"admin\",\"MINIO_ROOT_PASSWORD\":\"...\"}"

# 3. Rolling-restart — all existing JWTs are invalidated; users must re-login
kubectl rollout restart deployment/trustshield-api -n trustshield
```

### 4. Bank API Keys (application-level)

```bash
# Via admin API — old key is immediately invalidated
curl -X POST https://api.trustshield.in/api/v1/intel/banks/{bank_id}/regenerate-key \
  -H "Authorization: Bearer $ADMIN_TOKEN"

# New key is shown once — bank must store it securely
```

## Emergency Rotation

If a secret is suspected compromised:

1. Rotate immediately (do not wait for quarterly schedule)
2. Check CloudWatch / audit logs for unauthorized access
3. Notify affected parties (bank customers if a bank API key is compromised)
4. Document incident in postmortem

## Verification

After rotation:

1. Verify API starts successfully with new secrets
2. Verify existing users can still authenticate (except after JWT rotation)
3. Verify bank integrations work with new keys
4. Run integration tests: `pytest tests/integration/ -v`

## One-Time Manual Step: Terraform Remote State

Before first `terraform apply`, create the S3 state bucket and DynamoDB lock table manually:

```bash
# Create S3 bucket for Terraform state
aws s3api create-bucket \
  --bucket trustshield-terraform-state \
  --region ap-south-1 \
  --create-bucket-configuration LocationConstraint=ap-south-1

# Enable versioning
aws s3api put-bucket-versioning \
  --bucket trustshield-terraform-state \
  --versioning-configuration Status=Enabled

# Enable server-side encryption
aws s3api put-bucket-encryption \
  --bucket trustshield-terraform-state \
  --server-side-encryption-configuration '{
    "Rules": [{"ApplyServerSideEncryptionByDefault": {"SSEAlgorithm": "aws:kms"}}]
  }'

# Block public access
aws s3api put-public-access-block \
  --bucket trustshield-terraform-state \
  --public-access-block-configuration \
    BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true

# Create DynamoDB table for state locking
aws dynamodb create-table \
  --table-name trustshield-terraform-locks \
  --attribute-definitions AttributeName=LockID,AttributeType=S \
  --key-schema AttributeName=LockID,KeyType=HASH \
  --billing-mode PAY_PER_REQUEST \
  --region ap-south-1
```

After creation, update `infra/terraform/main.tf` to reference:
- S3 backend: `bucket = "trustshield-terraform-state"`
- DynamoDB lock table: `dynamodb_table = "trustshield-terraform-locks"`
