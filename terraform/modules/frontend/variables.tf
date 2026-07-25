variable "bucket_name" {
  description = "静的サイト配信用 S3 バケット名(グローバル一意)"
  type        = string
}

variable "domain_name" {
  description = "公開ドメイン名(例: code-narrative.ojos.jp)"
  type        = string
}

variable "zone_id" {
  description = "ドメインを収容する Route 53 ホストゾーン ID(委任済みサブドメインゾーン)"
  type        = string
}

variable "default_root_object" {
  description = "CloudFront のデフォルトルートオブジェクト"
  type        = string
  default     = "index.html"
}

variable "price_class" {
  description = "CloudFront の価格クラス(コスト最適化のため既定は北米/欧州)"
  type        = string
  default     = "PriceClass_100"
}
