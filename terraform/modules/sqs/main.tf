# 非同期変換ジョブ用の標準キューと DLQ(SPEC §2 / §4②)。
# at-least-once 配信のため、Worker 側は条件付き書き込みで冪等性を担保する前提。

resource "aws_sqs_queue" "dlq" {
  name                      = var.dlq_name
  message_retention_seconds = var.dlq_retention_seconds
  sqs_managed_sse_enabled   = true
}

resource "aws_sqs_queue" "main" {
  name                       = var.queue_name
  visibility_timeout_seconds = var.visibility_timeout_seconds
  message_retention_seconds  = var.retention_seconds
  sqs_managed_sse_enabled    = true

  # maxReceiveCount 超過分を DLQ へ退避する。
  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.dlq.arn
    maxReceiveCount     = var.max_receive_count
  })
}
