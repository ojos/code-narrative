output "bucket_name" {
  description = "静的サイト用 S3 バケット名(CI の s3 sync 対象)"
  value       = aws_s3_bucket.site.id
}

output "bucket_arn" {
  description = "S3 バケット ARN"
  value       = aws_s3_bucket.site.arn
}

output "distribution_id" {
  description = "CloudFront ディストリビューション ID(CI のキャッシュ無効化対象)"
  value       = aws_cloudfront_distribution.this.id
}

output "distribution_domain_name" {
  description = "CloudFront のデフォルトドメイン名"
  value       = aws_cloudfront_distribution.this.domain_name
}

output "certificate_arn" {
  description = "発行した ACM 証明書 ARN(us-east-1)"
  value       = aws_acm_certificate.cert.arn
}
