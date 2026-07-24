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
