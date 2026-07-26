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

# ホワイトリストから導出した Bedrock の許可 ARN 一式。
# terraform test の検証対象であり、権限まわりの調査時にも実値を確認できる。
# locals はモジュール外から参照できないため出力として露出する。
output "bedrock_resource_arns" {
  description = "Bedrock 呼び出しを許可する ARN(推論プロファイル + Foundation Model)"
  value       = local.bedrock_resource_arns
}
