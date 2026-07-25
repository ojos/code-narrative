variable "queue_name" {
  description = "メインキュー名"
  type        = string
}

variable "dlq_name" {
  description = "デッドレターキュー名"
  type        = string
}

variable "visibility_timeout_seconds" {
  description = "可視性タイムアウト。Worker Lambda タイムアウトの 6 倍以上を呼び出し側で設定する"
  type        = number
}

variable "max_receive_count" {
  description = "DLQ へ退避するまでの最大受信回数(maxReceiveCount)"
  type        = number
  default     = 5
}

variable "retention_seconds" {
  description = "メインキューのメッセージ保持秒数"
  type        = number
  default     = 345600 # 4 日
}

variable "dlq_retention_seconds" {
  description = "DLQ のメッセージ保持秒数(調査猶予のため長めに設定)"
  type        = number
  default     = 1209600 # 14 日
}

variable "dlq_alarm_threshold" {
  description = "DLQ 滞留メッセージ数の警報しきい値(これを超えると ALARM)"
  type        = number
  default     = 0
}

variable "alarm_actions" {
  description = "アラーム発報時の通知先(SNS トピック ARN 等)。既定は通知先なし"
  type        = list(string)
  default     = []
}
