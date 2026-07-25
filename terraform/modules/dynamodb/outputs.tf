output "table_name" {
  description = "DynamoDB テーブル名"
  value       = aws_dynamodb_table.this.name
}

output "table_arn" {
  description = "DynamoDB テーブルの ARN"
  value       = aws_dynamodb_table.this.arn
}

output "gsi_arn" {
  description = "GSI の ARN(IAM の Query 権限付与に使用)"
  value       = "${aws_dynamodb_table.this.arn}/index/${var.gsi_name}"
}

output "gsi_name" {
  description = "GSI 名"
  value       = var.gsi_name
}
