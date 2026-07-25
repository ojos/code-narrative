variable "function_name" {
  description = "API Lambda 関数名(関連リソースの命名基点にも用いる)"
  type        = string
}

variable "image_uri" {
  description = "API コンテナイメージの URI(<ecr_url>:<tag>)。初回 apply 前に push 済みである必要がある"
  type        = string
}

variable "timeout" {
  description = "Lambda タイムアウト秒数"
  type        = number
  default     = 30
}

variable "memory_size" {
  description = "Lambda メモリ(MB)"
  type        = number
  default     = 512
}

variable "log_retention_days" {
  description = "CloudWatch Logs の保持日数"
  type        = number
  default     = 30
}

variable "dynamodb_table_name" {
  description = "DynamoDB テーブル名(環境変数として注入)"
  type        = string
}

variable "dynamodb_table_arn" {
  description = "DynamoDB テーブル ARN(IAM 権限用)"
  type        = string
}

variable "dynamodb_gsi_arn" {
  description = "DynamoDB GSI ARN(Query 権限用)"
  type        = string
}

variable "sqs_queue_url" {
  description = "エンキュー先 SQS キュー URL(環境変数として注入)"
  type        = string
}

variable "sqs_queue_arn" {
  description = "エンキュー先 SQS キュー ARN(IAM 権限用)"
  type        = string
}

variable "cognito_user_pool_id" {
  description = "Cognito User Pool ID(環境変数として注入)"
  type        = string
}

variable "cognito_client_id" {
  description = "Cognito Client ID(JWT Authorizer の audience)"
  type        = string
}

variable "cognito_issuer" {
  description = "JWT Authorizer の issuer URL"
  type        = string
}

variable "bedrock_model_ids" {
  description = "許可モデルホワイトリスト(環境変数 MODEL_WHITELIST として注入)"
  type        = list(string)
}

variable "cors_allow_origins" {
  description = "CORS で許可するフロントエンド公開オリジン(SPA が別オリジンの execute-api を叩くため)"
  type        = list(string)
}

variable "extra_environment" {
  description = "追加の環境変数(任意)"
  type        = map(string)
  default     = {}
}
