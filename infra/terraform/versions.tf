terraform {
  required_version = ">= 1.6"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.0"
    }
  }

  backend "s3" {
    bucket         = "trustshield-terraform-state"
    key            = "infra/terraform.tfstate"
    region         = "ap-south-1"
    dynamodb_table = "trustshield-terraform-lock"
    encrypt        = true
  }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project     = "TrustShield"
      Environment = var.environment
      ManagedBy   = "Terraform"
    }
  }
}
