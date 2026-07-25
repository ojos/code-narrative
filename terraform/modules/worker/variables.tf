variable "function_name" {
  description = "Worker Lambda 関数名(関連リソースの命名基点にも用いる)"
  type        = string
}

variable "image_uri" {
  description = "Worker コンテナイメージの URI(<ecr_url>:<tag>)。初回 apply 前に push 済みである必要がある"
  type        = string
}

variable "timeout" {
  description = "Lambda タイムアウト秒数。SQS 可視性タイムアウトはこの 6 倍以上を設定する"
  type        = number
  default     = 300
}

variable "memory_size" {
  description = "Lambda メモリ(MB)。tarball 展開・解析のため大きめに設定"
  type        = number
  default     = 1024
}

variable "ephemeral_storage_mb" {
  description = "/tmp のサイズ(MB)。tarball 展開のため拡張する"
  type        = number
  default     = 2048
}

variable "log_retention_days" {
  description = "CloudWatch Logs の保持日数"
  type        = number
  default     = 30
}

variable "sqs_queue_arn" {
  description = "トリガー元 SQS キュー ARN"
  type        = string
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
  description = "DynamoDB GSI ARN(IAM 権限用)"
  type        = string
}

variable "bedrock_model_ids" {
  description = "許可モデルホワイトリスト。us. プレフィックスはクロスリージョン推論プロファイルとして扱う"
  type        = list(string)
}

variable "bedrock_region" {
  description = "Bedrock 呼び出しリージョン。クロスリージョン推論(us-)前提で us-east-1 を既定とする"
  type        = string
  default     = "us-east-1"
}

variable "batch_size" {
  description = "SQS イベントソースマッピングのバッチサイズ"
  type        = number
  default     = 1
}

variable "maximum_batching_window" {
  description = "バッチ収集の最大待機秒数"
  type        = number
  default     = 0
}

variable "max_concurrency" {
  description = "イベントソースマッピングの同時実行上限(Bedrock スロットリング回避)。2 以上"
  type        = number
  default     = 5

  validation {
    condition     = var.max_concurrency >= 2 && var.max_concurrency <= 1000
    error_message = "max_concurrency は 2〜1000 の範囲で指定してください。"
  }
}

variable "extra_environment" {
  description = "追加の環境変数(任意。GITHUB_TOKEN 等の機密は Secrets 参照で別途注入する)"
  type        = map(string)
  default     = {}
}
