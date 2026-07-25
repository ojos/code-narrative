terraform {
  # S3 ネイティブ state ロック(use_lockfile)を利用するため 1.10 以上を要求
  required_version = ">= 1.10"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.70, < 7.0"
    }
    tls = {
      source  = "hashicorp/tls"
      version = "~> 4.0"
    }
  }

  # 初回はローカル state で apply → 自身が作成したバケットへ移行済み(README 参照)。
  # 新規アカウントでゼロから作る場合のみ、初回 apply 時はこの backend ブロックを
  # 一時的にコメントアウトしてローカル state で実行すること。
  backend "s3" {}
}

provider "aws" {
  region = var.region

  default_tags {
    tags = {
      Project   = "code-narrative"
      ManagedBy = "terraform"
      Stack     = "bootstrap"
    }
  }
}
