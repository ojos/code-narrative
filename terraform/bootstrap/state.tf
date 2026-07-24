data "aws_caller_identity" "current" {}

locals {
  tfstate_bucket_name = coalesce(
    var.tfstate_bucket_name != "" ? var.tfstate_bucket_name : null,
    "code-narrative-tfstate-${data.aws_caller_identity.current.account_id}"
  )
}

# Terraform state 用 S3 バケット(ロックは S3 ネイティブ use_lockfile を利用するため DynamoDB は不要)
resource "aws_s3_bucket" "tfstate" {
  bucket = local.tfstate_bucket_name

  # state を含むため、誤削除防止。破棄が必要な場合は明示的に無効化する。
  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_s3_bucket_versioning" "tfstate" {
  bucket = aws_s3_bucket.tfstate.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "tfstate" {
  bucket = aws_s3_bucket.tfstate.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "aws:kms"
    }
    bucket_key_enabled = true
  }
}

resource "aws_s3_bucket_public_access_block" "tfstate" {
  bucket                  = aws_s3_bucket.tfstate.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}
