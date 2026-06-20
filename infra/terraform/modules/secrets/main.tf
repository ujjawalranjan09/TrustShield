resource "aws_secretsmanager_secret" "app" {
  for_each = toset(["db", "redis", "app"])

  name       = "${var.project}/${var.environment}/${each.key}"
  kms_key_id = var.kms_key_arn
}

resource "aws_secretsmanager_secret_version" "app" {
  for_each = toset(["db", "redis", "app"])

  secret_id = aws_secretsmanager_secret.app[each.key].id
  secret_string = jsonencode(each.key == "db" ? {
    database_url = var.database_url
  } : each.key == "redis" ? {
    redis_url = var.redis_url
  } : {
    jwt_secret          = var.jwt_secret
    pii_encryption_key  = var.pii_encryption_key
    kms_key_id          = var.kms_key_id
    stripe_secret_key   = var.stripe_secret_key
  })
}

variable "project" { type = string }
variable "environment" { type = string }
variable "kms_key_arn" { type = string }
variable "database_url" { type = string; sensitive = true }
variable "redis_url" { type = string; sensitive = true }
variable "jwt_secret" { type = string; sensitive = true }
variable "pii_encryption_key" { type = string; sensitive = true }
variable "kms_key_id" { type = string }
variable "stripe_secret_key" { type = string; sensitive = true }

output "secret_arns" {
  value = { for k, v in aws_secretsmanager_secret.app : k => v.arn }
}
