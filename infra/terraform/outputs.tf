output "kms_key_id" {
  description = "KMS key ID for encrypt/decrypt operations"
  value       = module.kms.key_id
  sensitive   = true
}

output "kms_key_arn" {
  description = "KMS key ARN"
  value       = module.kms.key_arn
}

output "rds_endpoint" {
  description = "RDS instance endpoint"
  value       = module.rds.endpoint
  sensitive   = true
}

output "redis_endpoint" {
  description = "ElastiCache Redis primary endpoint"
  value       = module.elasticache.primary_endpoint
  sensitive   = true
}

output "ml_artifacts_bucket" {
  description = "S3 bucket for ML model artifacts"
  value       = module.s3.ml_artifacts_bucket
}

output "backups_bucket" {
  description = "S3 bucket for compliance backups"
  value       = module.s3.backups_bucket
}

output "ecr_api_url" {
  description = "ECR repository URL for API image"
  value       = module.ecr.api_repo_url
}

output "ecr_worker_url" {
  description = "ECR repository URL for worker image"
  value       = module.ecr.worker_repo_url
}
