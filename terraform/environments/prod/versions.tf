terraform {
  required_version = ">= 1.10"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.70, < 7.0"
    }
  }

  # backend の具体値は backend.hcl で注入する:
  #   terraform init -backend-config=backend.hcl
  backend "s3" {
    key          = "prod/terraform.tfstate"
    use_lockfile = true
    encrypt      = true
  }
}

provider "aws" {
  region = var.region

  default_tags {
    tags = {
      Project     = "code-narrative"
      Environment = "prod"
      ManagedBy   = "terraform"
    }
  }
}

# CloudFront 用 ACM 証明書は us-east-1 でのみ発行可能なため別プロバイダーを用意
provider "aws" {
  alias  = "us_east_1"
  region = "us-east-1"

  default_tags {
    tags = {
      Project     = "code-narrative"
      Environment = "prod"
      ManagedBy   = "terraform"
    }
  }
}
