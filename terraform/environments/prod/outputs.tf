output "name_servers" {
  description = "サブドメインのネームサーバー。親ゾーン ojos.jp 側に NS レコードとして登録して委任する"
  value       = aws_route53_zone.subdomain.name_servers
}

output "hosted_zone_id" {
  description = "サブドメインのホストゾーン ID"
  value       = aws_route53_zone.subdomain.zone_id
}
