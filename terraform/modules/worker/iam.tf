# Worker Lambda の実行ロール。SQS 消費 / DynamoDB 更新 / Bedrock 呼び出しを
# 最小権限で許可する。Bedrock は許可モデルの ARN(推論プロファイル + Foundation
# Model)に限定する。

data "aws_caller_identity" "current" {}

locals {
  # us. プレフィックス付きはクロスリージョン推論プロファイル、それ以外は
  # Foundation Model を直接指定するモデルとして扱う。
  inference_profile_ids = [for m in var.bedrock_model_ids : m if startswith(m, "us.")]
  direct_model_ids      = [for m in var.bedrock_model_ids : m if !startswith(m, "us.")]

  # 推論プロファイル ARN(アカウント配下。リージョンは us- 系を跨ぐため * で許容しつつ
  # モデル ID で限定)。
  inference_profile_arns = [
    for m in local.inference_profile_ids :
    "arn:aws:bedrock:*:${data.aws_caller_identity.current.account_id}:inference-profile/${m}"
  ]

  # 推論プロファイルが実際にルーティングする Foundation Model の ARN(us. を除いた ID)。
  inference_fm_arns = [
    for m in local.inference_profile_ids :
    "arn:aws:bedrock:*::foundation-model/${trimprefix(m, "us.")}"
  ]

  # 直接指定モデルの Foundation Model ARN。
  direct_fm_arns = [
    for m in local.direct_model_ids :
    "arn:aws:bedrock:*::foundation-model/${m}"
  ]

  bedrock_resource_arns = concat(
    local.inference_profile_arns,
    local.inference_fm_arns,
    local.direct_fm_arns,
  )
}

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

resource "aws_iam_role_policy_attachment" "basic" {
  role       = aws_iam_role.this.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

data "aws_iam_policy_document" "app" {
  # SQS 消費(イベントソースマッピングが利用)。
  statement {
    sid    = "SqsConsume"
    effect = "Allow"
    actions = [
      "sqs:ReceiveMessage",
      "sqs:DeleteMessage",
      "sqs:GetQueueAttributes",
    ]
    resources = [var.sqs_queue_arn]
  }

  # ジョブレコードの読み書き。
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

  # Bedrock 呼び出し(許可モデルの ARN に限定)。
  statement {
    sid    = "BedrockInvoke"
    effect = "Allow"
    actions = [
      "bedrock:InvokeModel",
      "bedrock:InvokeModelWithResponseStream",
    ]
    resources = local.bedrock_resource_arns
  }
}

resource "aws_iam_role_policy" "app" {
  name   = "${var.function_name}-app"
  role   = aws_iam_role.this.id
  policy = data.aws_iam_policy_document.app.json
}
