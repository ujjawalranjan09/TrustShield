resource "aws_kms_key" "trustshield" {
  description             = "TrustShield encryption key for PII and data"
  deletion_window_in_days = 30
  enable_key_rotation     = true

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "AllowKeyAdministration"
        Effect    = "Allow"
        Principal = { AWS = "arn:aws:iam::${data.aws_caller_identity.current.account_id}:root" }
        Action    = "kms:*"
        Resource  = "*"
      },
      {
        Sid       = "AllowAPIAndWorkerUsage"
        Effect    = "Allow"
        Principal = { AWS = var.api_worker_role_arns }
        Action = [
          "kms:Encrypt",
          "kms:Decrypt",
          "kms:GenerateDataKey",
          "kms:ReEncryptFrom",
          "kms:ReEncryptTo",
          "kms:DescribeKey",
        ]
        Resource = "*"
      }
    ]
  })

  tags = {
    Name = "${var.project}-kms-${var.environment}"
  }
}

resource "aws_kms_alias" "trustshield" {
  name          = "alias/${var.project}-${var.environment}"
  target_key_id = aws_kms_key.trustshield.key_id
}

data "aws_caller_identity" "current" {}

variable "project" {
  type = string
}

variable "environment" {
  type = string
}

variable "api_worker_role_arns" {
  description = "IAM role ARNs for the API and worker services"
  type        = list(string)
}

output "key_id" {
  value = aws_kms_key.trustshield.key_id
}

output "key_arn" {
  value = aws_kms_key.trustshield.arn
}
