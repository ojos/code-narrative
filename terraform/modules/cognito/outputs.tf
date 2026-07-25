output "user_pool_id" {
  description = "Cognito User Pool ID"
  value       = aws_cognito_user_pool.this.id
}

output "user_pool_arn" {
  description = "Cognito User Pool ARN"
  value       = aws_cognito_user_pool.this.arn
}

output "client_id" {
  description = "User Pool Client ID(JWT Authorizer の audience)"
  value       = aws_cognito_user_pool_client.this.id
}

output "endpoint" {
  description = "User Pool のエンドポイント(cognito-idp.<region>.amazonaws.com/<pool_id>)。JWT issuer は https:// を前置して用いる"
  value       = aws_cognito_user_pool.this.endpoint
}

output "issuer" {
  description = "JWT Authorizer の issuer URL"
  value       = "https://${aws_cognito_user_pool.this.endpoint}"
}

output "hosted_ui_domain" {
  description = "Hosted UI ドメインプレフィックス"
  value       = aws_cognito_user_pool_domain.this.domain
}
