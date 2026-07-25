output "queue_url" {
  description = "メインキューの URL"
  value       = aws_sqs_queue.main.url
}

output "queue_arn" {
  description = "メインキューの ARN"
  value       = aws_sqs_queue.main.arn
}

output "queue_name" {
  description = "メインキュー名"
  value       = aws_sqs_queue.main.name
}

output "dlq_arn" {
  description = "DLQ の ARN"
  value       = aws_sqs_queue.dlq.arn
}

output "dlq_url" {
  description = "DLQ の URL"
  value       = aws_sqs_queue.dlq.url
}

output "dlq_name" {
  description = "DLQ 名"
  value       = aws_sqs_queue.dlq.name
}
