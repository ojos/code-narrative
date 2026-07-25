variable "region" {
  description = "主に利用する AWS リージョン"
  type        = string
  default     = "ap-northeast-1"
}

variable "github_owner" {
  description = "GitHub の組織/ユーザー名"
  type        = string
  default     = "ojos"
}

variable "github_repo" {
  description = "GitHub リポジトリ名"
  type        = string
  default     = "code-narrative"
}

variable "tfstate_bucket_name" {
  description = "Terraform state 用 S3 バケット名(グローバル一意)。空の場合はアカウントIDを付与して自動命名"
  type        = string
  default     = ""
}

variable "budget_limit_amount" {
  description = "月次予算のしきい値(当該アカウントは USD 請求。約20USD≒3,000円)"
  type        = string
  default     = "20"
}

variable "budget_currency" {
  description = "予算の通貨単位。当該アカウントの請求通貨は USD(AWS Budgets は USD のみ受付)"
  type        = string
  default     = "USD"
}

variable "notification_emails" {
  description = "Budgets / Cost Anomaly の通知先メールアドレス"
  type        = list(string)
  default     = ["aws+code-narrative@ojos.jp"]
}
