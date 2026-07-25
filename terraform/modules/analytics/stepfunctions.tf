# 集計バッチのステートマシン(SPEC §4④)。
# Scan ➔ 集計 ➔ 書き込み を集計 Lambda の直列 Task として実行する。
# 各 Task は同一 Lambda を phase 指定で呼び出し、結果を次段へ受け渡す。

data "aws_iam_policy_document" "sfn_assume" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["states.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "sfn" {
  name               = "${var.name_prefix}-sfn-role"
  assume_role_policy = data.aws_iam_policy_document.sfn_assume.json
}

# ステートマシンから集計 Lambda を呼び出す権限のみを付与する。
data "aws_iam_policy_document" "sfn_invoke" {
  statement {
    sid       = "InvokeStatsLambda"
    effect    = "Allow"
    actions   = ["lambda:InvokeFunction"]
    resources = [aws_lambda_function.stats.arn, "${aws_lambda_function.stats.arn}:*"]
  }
}

resource "aws_iam_role_policy" "sfn_invoke" {
  name   = "${var.name_prefix}-sfn-invoke"
  role   = aws_iam_role.sfn.id
  policy = data.aws_iam_policy_document.sfn_invoke.json
}

resource "aws_sfn_state_machine" "aggregate" {
  name     = "${var.name_prefix}-aggregate"
  role_arn = aws_iam_role.sfn.arn

  definition = jsonencode({
    Comment = "Daily aggregation: Scan -> Aggregate -> Write"
    StartAt = "Scan"
    States = {
      Scan = {
        Type     = "Task"
        Resource = "arn:aws:states:::lambda:invoke"
        Parameters = {
          FunctionName = aws_lambda_function.stats.arn
          Payload      = { phase = "scan" }
        }
        ResultSelector = { "items.$" = "$.Payload" }
        ResultPath     = "$.scan"
        Next           = "Aggregate"
      }
      Aggregate = {
        Type     = "Task"
        Resource = "arn:aws:states:::lambda:invoke"
        Parameters = {
          FunctionName = aws_lambda_function.stats.arn
          Payload = {
            phase    = "aggregate"
            "scan.$" = "$.scan.items"
          }
        }
        ResultSelector = { "metrics.$" = "$.Payload" }
        ResultPath     = "$.aggregate"
        Next           = "Write"
      }
      Write = {
        Type     = "Task"
        Resource = "arn:aws:states:::lambda:invoke"
        Parameters = {
          FunctionName = aws_lambda_function.stats.arn
          Payload = {
            phase       = "write"
            "metrics.$" = "$.aggregate.metrics"
          }
        }
        End = true
      }
    }
  })
}
