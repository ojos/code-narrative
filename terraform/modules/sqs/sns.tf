# DLQ 滞留アラームの通知先(SPEC §7 / 親 intake 受入#4)。
# トピックとアラーム連携は常に成立させ、メール購読は alarm_email 設定時のみ作成する。
# メールアドレスの値は tfvars 等で別管理し、コードにハードコードしない。

resource "aws_sns_topic" "alerts" {
  name = "${var.queue_name}-alerts"
}

resource "aws_sns_topic_subscription" "email" {
  count     = var.alarm_email != "" ? 1 : 0
  topic_arn = aws_sns_topic.alerts.arn
  protocol  = "email"
  endpoint  = var.alarm_email
}
