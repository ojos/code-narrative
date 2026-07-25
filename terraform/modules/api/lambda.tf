# REST API 本体(FastAPI + Mangum)。ECR コンテナイメージから起動する(SPEC §4①)。

resource "aws_cloudwatch_log_group" "lambda" {
  name              = "/aws/lambda/${var.function_name}"
  retention_in_days = var.log_retention_days
}

resource "aws_lambda_function" "this" {
  function_name = var.function_name
  role          = aws_iam_role.this.arn
  package_type  = "Image"
  image_uri     = var.image_uri
  timeout       = var.timeout
  memory_size   = var.memory_size

  environment {
    variables = merge({
      DYNAMODB_TABLE       = var.dynamodb_table_name
      SQS_QUEUE_URL        = var.sqs_queue_url
      COGNITO_USER_POOL_ID = var.cognito_user_pool_id
      COGNITO_CLIENT_ID    = var.cognito_client_id
      MODEL_WHITELIST      = join(",", var.bedrock_model_ids)
    }, var.extra_environment)
  }

  # ECR 先行作成の運用: 初回は image_uri で指定したイメージを参照するが、以降の
  # デプロイは CI が `aws lambda update-function-code` でイメージを直接差し替える。
  # そのため Terraform では image_uri の変化を無視し、コードデプロイとインフラ
  # 管理の責務を分離する(ドリフト誤検知の防止)。
  lifecycle {
    ignore_changes = [image_uri]
  }

  depends_on = [aws_cloudwatch_log_group.lambda]
}
