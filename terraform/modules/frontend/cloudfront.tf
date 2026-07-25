# CloudFront + S3(OAC)による静的配信(SPEC §4⑤ / §5)。

resource "aws_cloudfront_origin_access_control" "site" {
  name                              = "${var.bucket_name}-oac"
  description                       = "OAC for ${var.bucket_name}"
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

locals {
  s3_origin_id = "s3-${aws_s3_bucket.site.id}"
}

resource "aws_cloudfront_distribution" "this" {
  enabled             = true
  is_ipv6_enabled     = true
  comment             = "code-narrative frontend"
  default_root_object = var.default_root_object
  price_class         = var.price_class

  # 独自ドメイン(エイリアス)は ACM 証明書とセットでのみ有効。NS 委任完了前は
  # エイリアスを付けず *.cloudfront.net の暫定配信とする。
  aliases = var.dns_delegation_ready ? [var.domain_name] : []

  origin {
    domain_name              = aws_s3_bucket.site.bucket_regional_domain_name
    origin_id                = local.s3_origin_id
    origin_access_control_id = aws_cloudfront_origin_access_control.site.id
  }

  default_cache_behavior {
    target_origin_id       = local.s3_origin_id
    viewer_protocol_policy = "redirect-to-https"
    allowed_methods        = ["GET", "HEAD", "OPTIONS"]
    cached_methods         = ["GET", "HEAD"]
    compress               = true

    # AWS 管理ポリシー CachingOptimized。
    cache_policy_id = "658327ea-f89d-4fab-a63d-7e88639e58f6"
  }

  # SPA ルーティングのため 403/404 を index.html にフォールバックする。
  custom_error_response {
    error_code            = 403
    response_code         = 200
    response_page_path    = "/${var.default_root_object}"
    error_caching_min_ttl = 10
  }

  custom_error_response {
    error_code            = 404
    response_code         = 200
    response_page_path    = "/${var.default_root_object}"
    error_caching_min_ttl = 10
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  # NS 委任完了前(dns_delegation_ready=false)は CloudFront デフォルト証明書で暫定配信し、
  # 委任・ACM 検証完了後(true)に独自ドメイン用 ACM 証明書へ切り替える。
  viewer_certificate {
    cloudfront_default_certificate = var.dns_delegation_ready ? null : true
    acm_certificate_arn            = one(aws_acm_certificate_validation.cert[*].certificate_arn)
    ssl_support_method             = var.dns_delegation_ready ? "sni-only" : null
    minimum_protocol_version       = var.dns_delegation_ready ? "TLSv1.2_2021" : null
  }
}
