output "name_servers" {
  description = "サブドメインのネームサーバー。親ゾーン ojos.jp 側に NS レコードとして登録して委任する"
  value       = aws_route53_zone.subdomain.name_servers
}

output "hosted_zone_id" {
  description = "サブドメインのホストゾーン ID"
  value       = aws_route53_zone.subdomain.zone_id
}

# --- アプリ基盤(CI/CD が参照する識別子) ---

output "api_endpoint" {
  description = "HTTP API のエンドポイント URL"
  value       = module.api.api_endpoint
}

output "ecr_api_repository_url" {
  description = "API イメージの ECR リポジトリ URL(CI の push 先)"
  value       = module.ecr_api.repository_url
}

output "ecr_worker_repository_url" {
  description = "Worker イメージの ECR リポジトリ URL(CI の push 先)"
  value       = module.ecr_worker.repository_url
}

output "ecr_stats_repository_url" {
  description = "集計 Lambda イメージの ECR リポジトリ URL(CI の push 先)"
  value       = module.ecr_stats.repository_url
}

output "api_function_name" {
  description = "API Lambda 関数名(CI の update-function-code 対象)"
  value       = module.api.function_name
}

output "worker_function_name" {
  description = "Worker Lambda 関数名(CI の update-function-code 対象)"
  value       = module.worker.function_name
}

output "stats_function_name" {
  description = "集計 Lambda 関数名(CI の update-function-code 対象)"
  value       = module.analytics.stats_function_name
}

output "dynamodb_table_name" {
  description = "DynamoDB テーブル名"
  value       = module.dynamodb.table_name
}

output "sqs_queue_url" {
  description = "ジョブ投入先 SQS キュー URL"
  value       = module.sqs.queue_url
}

output "cognito_user_pool_id" {
  description = "Cognito User Pool ID(フロントエンド設定用)"
  value       = module.cognito.user_pool_id
}

output "cognito_client_id" {
  description = "Cognito Client ID(フロントエンド設定用)"
  value       = module.cognito.client_id
}

output "cognito_hosted_ui_domain" {
  description = "Cognito Hosted UI ドメインプレフィックス"
  value       = module.cognito.hosted_ui_domain
}

output "cloudfront_distribution_id" {
  description = "CloudFront ディストリビューション ID(CI のキャッシュ無効化対象)"
  value       = module.frontend.distribution_id
}

output "frontend_bucket_name" {
  description = "フロントエンド配信用 S3 バケット名(CI の s3 sync 対象)"
  value       = module.frontend.bucket_name
}
