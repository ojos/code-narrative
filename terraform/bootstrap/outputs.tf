output "tfstate_bucket" {
  description = "Terraform state 用 S3 バケット名。prod スタックの backend 設定に使う"
  value       = aws_s3_bucket.tfstate.id
}

output "github_oidc_provider_arn" {
  description = "GitHub Actions OIDC プロバイダーの ARN"
  value       = aws_iam_openid_connect_provider.github_actions.arn
}

output "terraform_plan_role_arn" {
  description = "PR での terraform plan 用ロール ARN。GitHub Actions の role-to-assume に設定"
  value       = aws_iam_role.terraform_plan.arn
}

output "terraform_apply_role_arn" {
  description = "main での terraform apply 用ロール ARN。GitHub Actions の role-to-assume に設定"
  value       = aws_iam_role.terraform_apply.arn
}
