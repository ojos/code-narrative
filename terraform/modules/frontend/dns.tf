# 公開ドメインを CloudFront に向ける A / AAAA エイリアスレコード。
# 委任済みサブドメインゾーン(prod の aws_route53_zone.subdomain)に追加する。
# 独自ドメインは CloudFront にエイリアスが設定されて初めて機能するため、NS 委任完了
# (dns_delegation_ready=true)後にのみ作成する。

resource "aws_route53_record" "a" {
  count   = var.dns_delegation_ready ? 1 : 0
  zone_id = var.zone_id
  name    = var.domain_name
  type    = "A"

  alias {
    name                   = aws_cloudfront_distribution.this.domain_name
    zone_id                = aws_cloudfront_distribution.this.hosted_zone_id
    evaluate_target_health = false
  }
}

resource "aws_route53_record" "aaaa" {
  count   = var.dns_delegation_ready ? 1 : 0
  zone_id = var.zone_id
  name    = var.domain_name
  type    = "AAAA"

  alias {
    name                   = aws_cloudfront_distribution.this.domain_name
    zone_id                = aws_cloudfront_distribution.this.hosted_zone_id
    evaluate_target_health = false
  }
}
