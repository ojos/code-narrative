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

variable "dns_delegation_ready" {
  description = <<-EOT
    親ゾーン ojos.jp への NS 委任が完了しているか。
    false(既定): DNS 委任完了に依存するリソースを作らない。ACM 検証完了(待機)、
                 CloudFront の独自ドメイン紐付け(ACM 証明書・エイリアス)、A/AAAA を無効化し、
                 CloudFront はデフォルト証明書で *.cloudfront.net として暫定配信する。
    true       : NS 委任後に指定し、ACM 検証・独自ドメイン配信・A/AAAA を完成させる。
  EOT
  type        = bool
  default     = false
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
