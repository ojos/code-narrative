variable "table_name" {
  description = "DynamoDB テーブル名"
  type        = string
  default     = "CodeNarratives"
}

variable "gsi_name" {
  description = "ユーザー別ジョブ一覧用 GSI 名"
  type        = string
  default     = "user_id-created_at-index"
}

variable "point_in_time_recovery" {
  description = "ポイントインタイムリカバリを有効化するか"
  type        = bool
  default     = true
}
