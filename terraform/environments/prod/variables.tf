variable "region" {
  description = "主に利用する AWS リージョン"
  type        = string
  default     = "ap-northeast-1"
}

variable "subdomain" {
  description = "公開用サブドメイン(親ゾーン ojos.jp へ委任する)"
  type        = string
  default     = "code-narrative.ojos.jp"
}

variable "bedrock_model_ids" {
  description = "許可モデルホワイトリスト(SPEC §4⑤)。地理スコープ付き ID(jp. 等)は推論プロファイル。デプロイ先 ap-northeast-1(東京)で提供され、temperature 指定に対応するモデルをベンダー重複なしで選定"
  type        = list(string)
  default = [
    "jp.anthropic.claude-sonnet-4-5-20250929-v1:0",
    "amazon.nova-lite-v1:0",
    "deepseek.v3.2",
    "qwen.qwen3-32b-v1:0",
    "google.gemma-3-12b-it",
  ]
}

variable "hosted_ui_domain_prefix" {
  description = "Cognito Hosted UI のドメインプレフィックス(リージョン内で一意)"
  type        = string
  default     = "code-narrative-auth"
}

variable "api_image_tag" {
  description = "API Lambda が参照する ECR イメージタグ(CI が push するタグ)"
  type        = string
  default     = "latest"
}

variable "worker_image_tag" {
  description = "Worker Lambda が参照する ECR イメージタグ"
  type        = string
  default     = "latest"
}

variable "stats_image_tag" {
  description = "集計 Lambda が参照する ECR イメージタグ"
  type        = string
  default     = "latest"
}

variable "enable_analytics" {
  description = <<-EOT
    集計バッチ(stats Lambda / Step Functions / Scheduler / stats ECR)を作成するか。
    false(既定): apps/lambda-stats 未実装でイメージが無いため作らない(全体 apply が成功)。
    true       : stats アプリ実装後に有効化(ECR 先行作成 → image push → apply)。
  EOT
  type        = bool
  default     = false
}

variable "worker_max_concurrency" {
  description = "Worker イベントソースマッピングの同時実行上限(Bedrock スロットリング回避)"
  type        = number
  default     = 5
}

variable "sqs_max_receive_count" {
  description = "DLQ へ退避するまでの最大受信回数"
  type        = number
  default     = 5
}

variable "dns_delegation_ready" {
  description = <<-EOT
    親ゾーン ojos.jp への NS 委任が完了しているか(二段階 apply の切替)。
    false(既定): まずこの状態で apply し `terraform output name_servers` を取得、
                 さくら会員メニューで親 ojos.jp に NS 委任する。ACM 検証・独自ドメイン
                 配信・A/AAAA は作成されず、CloudFront は *.cloudfront.net で暫定配信。
    true       : NS 委任後に指定して再 apply し、ACM 検証と独自ドメイン配信を完成させる。
  EOT
  type        = bool
  default     = false
}

variable "cors_allow_origins" {
  description = "API Gateway の CORS で許可するフロントエンド公開オリジン"
  type        = list(string)
  default     = ["https://code-narrative.ojos.jp"]
}

variable "alarm_email" {
  description = "DLQ アラーム通知先メールアドレス。空なら購読を作らない(値は tfvars で管理しハードコードしない)"
  type        = string
  default     = ""
}
