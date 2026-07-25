output "api_endpoint" {
  description = "HTTP API のエンドポイント URL($default ステージ)"
  value       = aws_apigatewayv2_stage.default.invoke_url
}

output "api_id" {
  description = "HTTP API ID"
  value       = aws_apigatewayv2_api.this.id
}

output "function_name" {
  description = "API Lambda 関数名(CI のコード更新対象)"
  value       = aws_lambda_function.this.function_name
}

output "function_arn" {
  description = "API Lambda 関数 ARN"
  value       = aws_lambda_function.this.arn
}

output "role_arn" {
  description = "API Lambda 実行ロール ARN"
  value       = aws_iam_role.this.arn
}
