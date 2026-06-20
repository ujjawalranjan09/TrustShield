resource "aws_security_group" "redis" {
  name_prefix = "${var.project}-redis-${var.environment}"
  vpc_id      = var.vpc_id

  ingress {
    from_port       = 6379
    to_port         = 6379
    protocol        = "tcp"
    security_groups = var.allowed_security_group_ids
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = { Name = "${var.project}-redis-sg-${var.environment}" }
}

resource "aws_elasticache_replication_group" "trustshield" {
  replication_group_id = "${var.project}-redis-${var.environment}"
  description          = "TrustShield Redis cluster"

  node_type            = var.node_type
  num_cache_clusters   = 2
  port                 = 6379
  parameter_group_name = "default.redis7"

  automatic_failover_enabled = true
  multi_az_enabled           = true

  at_rest_encryption_enabled = true
  transit_encryption_enabled = true
  auth_token                = var.auth_token

  subnet_group_name  = aws_elasticache_subnet_group.trustshield.name
  security_group_ids = [aws_security_group.redis.id]

  tags = {
    Name = "${var.project}-redis-${var.environment}"
  }
}

resource "aws_elasticache_subnet_group" "trustshield" {
  name       = "${var.project}-redis-${var.environment}"
  subnet_ids = var.private_subnet_ids
}

variable "project" { type = string }
variable "environment" { type = string }
variable "vpc_id" { type = string }
variable "private_subnet_ids" { type = list(string) }
variable "allowed_security_group_ids" { type = list(string) }
variable "node_type" { type = string }
variable "auth_token" { type = string; sensitive = true }

output "primary_endpoint" {
  value = aws_elasticache_replication_group.trustshield.primary_endpoint_address
}
