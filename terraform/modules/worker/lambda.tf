# SQS Worker 本体(Go / Bedrock Converse)。ECR コンテナイメージから起動する(SPEC §4②)。

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

  ephemeral_storage {
    size = var.ephemeral_storage_mb
  }

  environment {
    variables = merge({
      DYNAMODB_TABLE  = var.dynamodb_table_name
      MODEL_WHITELIST = join(",", var.bedrock_model_ids)
      BEDROCK_REGION  = var.bedrock_region
    }, var.extra_environment)
  }

  # ECR 先行作成の運用: 以降のデプロイは CI が update-function-code で差し替えるため
  # image_uri の変化を無視する(api モジュールと同方針)。
  lifecycle {
    ignore_changes = [image_uri]
  }

  depends_on = [aws_cloudwatch_log_group.lambda]
}

# SQS トリガー。maxConcurrency で Bedrock スロットリングを回避し、
# ReportBatchItemFailures で部分バッチ失敗のみ再配信する(SPEC §4②)。
resource "aws_lambda_event_source_mapping" "sqs" {
  event_source_arn                   = var.sqs_queue_arn
  function_name                      = aws_lambda_function.this.arn
  batch_size                         = var.batch_size
  maximum_batching_window_in_seconds = var.maximum_batching_window
  function_response_types            = ["ReportBatchItemFailures"]

  scaling_config {
    maximum_concurrency = var.max_concurrency
  }
}
