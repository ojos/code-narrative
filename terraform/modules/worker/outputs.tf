output "function_name" {
  description = "Worker Lambda 関数名(CI のコード更新対象)"
  value       = aws_lambda_function.this.function_name
}

output "function_arn" {
  description = "Worker Lambda 関数 ARN"
  value       = aws_lambda_function.this.arn
}

output "role_arn" {
  description = "Worker Lambda 実行ロール ARN"
  value       = aws_iam_role.this.arn
}
