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
  description = "許可モデルホワイトリスト(SPEC §4⑤)。us. プレフィックスはクロスリージョン推論プロファイル"
  type        = list(string)
  default = [
    "us.anthropic.claude-sonnet-4-5-20250929-v1:0",
    "amazon.nova-lite-v1:0",
    "us.meta.llama3-3-70b-instruct-v1:0",
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
