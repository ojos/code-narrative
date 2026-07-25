# API Lambda の実行ロール。最小権限で DynamoDB / SQS / Logs のみを許可する。

data "aws_iam_policy_document" "assume" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "this" {
  name               = "${var.function_name}-role"
  assume_role_policy = data.aws_iam_policy_document.assume.json
}

# 構造化ログ出力のための基本実行権限(CloudWatch Logs)。
resource "aws_iam_role_policy_attachment" "basic" {
  role       = aws_iam_role.this.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

data "aws_iam_policy_document" "app" {
  statement {
    sid    = "DynamoDbJobAccess"
    effect = "Allow"
    actions = [
      "dynamodb:GetItem",
      "dynamodb:PutItem",
      "dynamodb:UpdateItem",
      "dynamodb:Query",
    ]
    resources = [
      var.dynamodb_table_arn,
      var.dynamodb_gsi_arn,
    ]
  }

  statement {
    sid       = "SqsEnqueue"
    effect    = "Allow"
    actions   = ["sqs:SendMessage"]
    resources = [var.sqs_queue_arn]
  }
}

resource "aws_iam_role_policy" "app" {
  name   = "${var.function_name}-app"
  role   = aws_iam_role.this.id
  policy = data.aws_iam_policy_document.app.json
}
