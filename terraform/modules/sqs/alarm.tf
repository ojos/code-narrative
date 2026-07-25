# DLQ に滞留したメッセージ数を監視し、変換処理の失敗を検知する(SPEC §7)。
resource "aws_cloudwatch_metric_alarm" "dlq_messages" {
  alarm_name          = "${var.dlq_name}-messages-visible"
  namespace           = "AWS/SQS"
  metric_name         = "ApproximateNumberOfMessagesVisible"
  statistic           = "Maximum"
  period              = 300
  evaluation_periods  = 1
  threshold           = var.dlq_alarm_threshold
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"
  alarm_description   = "DLQ に処理失敗メッセージが滞留しています(変換失敗の可能性)"

  dimensions = {
    QueueName = aws_sqs_queue.dlq.name
  }

  alarm_actions = concat([aws_sns_topic.alerts.arn], var.alarm_actions)
  ok_actions    = concat([aws_sns_topic.alerts.arn], var.alarm_actions)
}
