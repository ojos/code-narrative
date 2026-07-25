# CloudFront 用 ACM 証明書。us-east-1 でのみ発行可能なため us_east_1 プロバイダを使用。
# 検証は委任済みサブドメインゾーンへの DNS レコードで行う。
#
# 証明書リソースと検証用 DNS レコードは常に作成する(委任前でも作成自体はブロックしない)。
# 一方、検証完了を待機する aws_acm_certificate_validation は、親 ojos.jp への NS 委任が
# 完了する(dns_delegation_ready=true)まで作成しない。委任前にフル apply すると DNS 検証が
# タイムアウトして apply 全体が失敗する鶏卵問題を避けるための二段階 apply とする。

resource "aws_acm_certificate" "cert" {
  provider          = aws.us_east_1
  domain_name       = var.domain_name
  validation_method = "DNS"

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_route53_record" "cert_validation" {
  for_each = {
    for dvo in aws_acm_certificate.cert.domain_validation_options : dvo.domain_name => {
      name   = dvo.resource_record_name
      record = dvo.resource_record_value
      type   = dvo.resource_record_type
    }
  }

  zone_id         = var.zone_id
  name            = each.value.name
  type            = each.value.type
  records         = [each.value.record]
  ttl             = 60
  allow_overwrite = true
}

resource "aws_acm_certificate_validation" "cert" {
  count                   = var.dns_delegation_ready ? 1 : 0
  provider                = aws.us_east_1
  certificate_arn         = aws_acm_certificate.cert.arn
  validation_record_fqdns = [for r in aws_route53_record.cert_validation : r.fqdn]
}
