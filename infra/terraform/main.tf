module "kms" {
  source = "./modules/kms"

  project              = var.project
  environment          = var.environment
  api_worker_role_arns = var.api_worker_role_arns
}

module "rds" {
  source = "./modules/rds"

  project                   = var.project
  environment               = var.environment
  vpc_id                    = var.vpc_id
  private_subnet_ids        = var.private_subnet_ids
  allowed_security_group_ids = var.allowed_security_group_ids
  instance_class            = var.db_instance_class
  multi_az                  = var.db_multi_az
  db_name                   = var.db_name
  db_username               = var.db_username
  db_password               = var.db_password
  kms_key_arn               = module.kms.key_arn
}

module "elasticache" {
  source = "./modules/elasticache"

  project                   = var.project
  environment               = var.environment
  vpc_id                    = var.vpc_id
  private_subnet_ids        = var.private_subnet_ids
  allowed_security_group_ids = var.allowed_security_group_ids
  node_type                 = var.redis_node_type
  auth_token                = var.redis_auth_token
}

module "s3" {
  source = "./modules/s3"

  project     = var.project
  environment = var.environment
  kms_key_arn = module.kms.key_arn
}

module "secrets" {
  source = "./modules/secrets"

  project            = var.project
  environment        = var.environment
  kms_key_arn        = module.kms.key_arn
  database_url       = "postgresql+asyncpg://${var.db_username}:${var.db_password}@${module.rds.endpoint}/${var.db_name}"
  redis_url          = "rediss://:${var.redis_auth_token}@${module.elasticache.primary_endpoint}:6379"
  jwt_secret         = var.jwt_secret
  pii_encryption_key = var.pii_encryption_key
  kms_key_id         = module.kms.key_id
  stripe_secret_key  = var.stripe_secret_key
}

module "ecr" {
  source = "./modules/ecr"

  project      = var.project
  kms_key_arn  = module.kms.key_arn
  image_count  = var.ecr_image_count
}
