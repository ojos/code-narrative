output "repository_url" {
  description = "ECR リポジトリの URL(イメージ参照 <url>:<tag> の基点)"
  value       = aws_ecr_repository.this.repository_url
}

output "repository_arn" {
  description = "ECR リポジトリの ARN"
  value       = aws_ecr_repository.this.arn
}

output "repository_name" {
  description = "ECR リポジトリ名"
  value       = aws_ecr_repository.this.name
}
