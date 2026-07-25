# 集計 Lambda(SPEC §4④)。Step Functions の各 Task から phase を切り替えて呼び出す。
# ※ 集計 Lambda のアプリ本体(イメージ)は別タスクで実装・push する前提。本モジュールは
#    インフラ(関数・ロール・状態機械・スケジュール)のみを構築する。
# コンテナイメージ運用は api / worker と同じ ECR 先行作成方針に従う。

data "aws_iam_policy_document" "stats_assume" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "stats" {
  name               = "${var.name_prefix}-stats-role"
  assume_role_policy = data.aws_iam_policy_document.stats_assume.json
}

resource "aws_iam_role_policy_attachment" "stats_basic" {
  role       = aws_iam_role.stats.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# Scan による集計と STATS# レコードの書き込み。
data "aws_iam_policy_document" "stats_app" {
  statement {
    sid    = "DynamoDbAggregate"
    effect = "Allow"
    actions = [
      "dynamodb:Scan",
      "dynamodb:Query",
      "dynamodb:PutItem",
    ]
    resources = [
      var.dynamodb_table_arn,
      var.dynamodb_gsi_arn,
    ]
  }
}

resource "aws_iam_role_policy" "stats_app" {
  name   = "${var.name_prefix}-stats-app"
  role   = aws_iam_role.stats.id
  policy = data.aws_iam_policy_document.stats_app.json
}

resource "aws_cloudwatch_log_group" "stats" {
  name              = "/aws/lambda/${var.name_prefix}-stats"
  retention_in_days = var.log_retention_days
}

resource "aws_lambda_function" "stats" {
  function_name = "${var.name_prefix}-stats"
  role          = aws_iam_role.stats.arn
  package_type  = "Image"
  image_uri     = var.stats_image_uri
  timeout       = var.stats_timeout
  memory_size   = var.stats_memory_size

  environment {
    variables = {
      DYNAMODB_TABLE = var.dynamodb_table_name
    }
  }

  lifecycle {
    ignore_changes = [image_uri]
  }

  depends_on = [aws_cloudwatch_log_group.stats]
}
