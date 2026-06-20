resource "aws_db_subnet_group" "trustshield" {
  name       = "${var.project}-db-${var.environment}"
  subnet_ids = var.private_subnet_ids

  tags = { Name = "${var.project}-db-${var.environment}" }
}

resource "aws_security_group" "rds" {
  name_prefix = "${var.project}-rds-${var.environment}"
  vpc_id      = var.vpc_id

  ingress {
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = var.allowed_security_group_ids
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = { Name = "${var.project}-rds-sg-${var.environment}" }
}

resource "aws_db_parameter_group" "trustshield" {
  name   = "${var.project}-pg16-${var.environment}"
  family = "postgres16"

  parameter {
    name  = "log_statement"
    value = "ddl"
  }

  parameter {
    name  = "rds.log_connections"
    value = "1"
  }
}

resource "aws_db_instance" "trustshield" {
  identifier = "${var.project}-db-${var.environment}"

  engine         = "postgres"
  engine_version = "16"
  instance_class = var.instance_class

  allocated_storage     = 20
  max_allocated_storage = 100
  storage_type          = "gp3"
  storage_encrypted     = true
  kms_key_id            = var.kms_key_arn

  db_name  = var.db_name
  username = var.db_username
  password = var.db_password

  multi_az            = var.multi_az
  publicly_accessible = false
  skip_final_snapshot = var.environment != "prod"
  final_snapshot_identifier = var.environment == "prod" ? "${var.project}-db-final-${var.environment}" : null

  backup_retention_period = 30
  backup_window           = "03:00-04:00"
  maintenance_window      = "sun:04:00-sun:05:00"

  deletion_protection = var.environment == "prod"

  db_subnet_group_name   = aws_db_subnet_group.trustshield.name
  vpc_security_group_ids = [aws_security_group.rds.id]
  parameter_group_name   = aws_db_parameter_group.trustshield.name

  tags = {
    Name = "${var.project}-db-${var.environment}"
  }
}

resource "aws_secretsmanager_secret" "db_password" {
  name       = "${var.project}/${var.environment}/db"
  kms_key_id = var.kms_key_arn
}

resource "aws_secretsmanager_secret_version" "db_password" {
  secret_id = aws_secretsmanager_secret.db_password.id
  secret_string = jsonencode({
    database_url = "postgresql+asyncpg://${var.db_username}:${var.db_password}@${aws_db_instance.trustshield.endpoint}/${var.db_name}"
  })
}

variable "project" { type = string }
variable "environment" { type = string }
variable "vpc_id" { type = string }
variable "private_subnet_ids" { type = list(string) }
variable "allowed_security_group_ids" { type = list(string) }
variable "instance_class" { type = string }
variable "multi_az" { type = bool }
variable "db_name" { type = string }
variable "db_username" { type = string }
variable "db_password" { type = string; sensitive = true }
variable "kms_key_arn" { type = string }

output "endpoint" {
  value = aws_db_instance.trustshield.endpoint
}

output "arn" {
  value = aws_db_instance.trustshield.arn
}

output "secret_arn" {
  value = aws_secretsmanager_secret.db_password.arn
}
