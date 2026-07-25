variable "name_prefix" {
  description = "集計バッチ関連リソースの命名プレフィックス"
  type        = string
}

variable "stats_image_uri" {
  description = "集計 Lambda コンテナイメージの URI(<ecr_url>:<tag>)。初回 apply 前に push 済みである必要がある"
  type        = string
}

variable "stats_timeout" {
  description = "集計 Lambda のタイムアウト秒数"
  type        = number
  default     = 300
}

variable "stats_memory_size" {
  description = "集計 Lambda のメモリ(MB)"
  type        = number
  default     = 512
}

variable "log_retention_days" {
  description = "CloudWatch Logs の保持日数"
  type        = number
  default     = 30
}

variable "dynamodb_table_name" {
  description = "集計対象 DynamoDB テーブル名(環境変数として注入)"
  type        = string
}

variable "dynamodb_table_arn" {
  description = "集計対象 DynamoDB テーブル ARN(IAM 権限用)"
  type        = string
}

variable "dynamodb_gsi_arn" {
  description = "DynamoDB GSI ARN(IAM 権限用)"
  type        = string
}

variable "schedule_expression" {
  description = "EventBridge Scheduler の実行スケジュール(日次)"
  type        = string
  default     = "rate(1 day)"
}

variable "schedule_timezone" {
  description = "スケジュールのタイムゾーン"
  type        = string
  default     = "Asia/Tokyo"
}
