# 集計バッチの日次起動(SPEC §4④)。EventBridge Scheduler がステートマシンを起動する。

data "aws_iam_policy_document" "scheduler_assume" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["scheduler.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "scheduler" {
  name               = "${var.name_prefix}-scheduler-role"
  assume_role_policy = data.aws_iam_policy_document.scheduler_assume.json
}

data "aws_iam_policy_document" "scheduler_start" {
  statement {
    sid       = "StartAggregateExecution"
    effect    = "Allow"
    actions   = ["states:StartExecution"]
    resources = [aws_sfn_state_machine.aggregate.arn]
  }
}

resource "aws_iam_role_policy" "scheduler_start" {
  name   = "${var.name_prefix}-scheduler-start"
  role   = aws_iam_role.scheduler.id
  policy = data.aws_iam_policy_document.scheduler_start.json
}

resource "aws_scheduler_schedule" "daily" {
  name = "${var.name_prefix}-daily-aggregate"

  flexible_time_window {
    mode = "OFF"
  }

  schedule_expression          = var.schedule_expression
  schedule_expression_timezone = var.schedule_timezone

  target {
    arn      = aws_sfn_state_machine.aggregate.arn
    role_arn = aws_iam_role.scheduler.arn
  }
}
