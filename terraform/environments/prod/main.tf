# アプリ基盤一式(SPEC Phase 2 / §5)。責務ごとに terraform/modules/ 配下の
# モジュールへ分割し、ここから配線する。VPC を構築しないフルサーバーレス構成。
#
# 【ECR 先行作成と初回 apply の順序】
# Lambda(コンテナイメージ)は ECR リポジトリの URI を参照するが、初回 apply 時点では
# まだイメージが push されていない。そのため CI(deploy.yml)は次の順で適用する:
#   1) ECR リポジトリを先行作成      : terraform apply -target=module.ecr_api ...
#   2) 各イメージをビルドして push     : docker build & push(:latest)
#   3) 全体を apply                   : Lambda がイメージを参照して作成される
# 以降のコードデプロイは CI が `aws lambda update-function-code` で直接差し替えるため、
# 各 Lambda モジュールは lifecycle.ignore_changes=[image_uri] でドリフトを無視する。

data "aws_caller_identity" "current" {}

locals {
  name_prefix = "code-narrative"

  # 許可モデルホワイトリスト(SPEC §4⑤)。us. プレフィックスはクロスリージョン推論プロファイル。
  bedrock_model_ids = var.bedrock_model_ids

  # 静的サイト用バケットはグローバル一意にするためアカウント ID を付与する。
  frontend_bucket_name = "${local.name_prefix}-frontend-${data.aws_caller_identity.current.account_id}"

  # 公開ドメイン(委任済みサブドメイン)。
  frontend_domain = var.subdomain

  # Worker のタイムアウトと SQS 可視性タイムアウト(6 倍以上)。
  worker_timeout         = 300
  sqs_visibility_timeout = local.worker_timeout * 6
}

# --- ECR(API / Worker / Stats それぞれのコンテナレジストリ) ---

module "ecr_api" {
  source          = "../../modules/ecr"
  repository_name = "${local.name_prefix}-api"
}

module "ecr_worker" {
  source          = "../../modules/ecr"
  repository_name = "${local.name_prefix}-worker"
}

# stats(集計バッチ)は apps/lambda-stats 未実装でイメージが存在しないため、既定では作らない。
# stats アプリ実装後に enable_analytics=true で ECR 先行作成 → image push → 有効化する。
module "ecr_stats" {
  count           = var.enable_analytics ? 1 : 0
  source          = "../../modules/ecr"
  repository_name = "${local.name_prefix}-stats"
}

# --- DynamoDB(ジョブ・集計レコード) ---

module "dynamodb" {
  source     = "../../modules/dynamodb"
  table_name = "CodeNarratives"
}

# --- SQS(標準キュー + DLQ + DLQ 滞留アラーム) ---

module "sqs" {
  source                     = "../../modules/sqs"
  queue_name                 = "${local.name_prefix}-jobs"
  dlq_name                   = "${local.name_prefix}-jobs-dlq"
  visibility_timeout_seconds = local.sqs_visibility_timeout
  max_receive_count          = var.sqs_max_receive_count
  alarm_email                = var.alarm_email
}

# --- Cognito(User Pool / Client(Auth Code + PKCE) / Hosted UI) ---

module "cognito" {
  source                  = "../../modules/cognito"
  user_pool_name          = "${local.name_prefix}-users"
  client_name             = "${local.name_prefix}-web"
  hosted_ui_domain_prefix = var.hosted_ui_domain_prefix
  callback_urls           = ["https://${local.frontend_domain}/callback"]
  logout_urls             = ["https://${local.frontend_domain}/"]
}

# --- API(Python Lambda + API Gateway HTTP API + JWT Authorizer) ---

module "api" {
  source        = "../../modules/api"
  function_name = "${local.name_prefix}-api"
  image_uri     = "${module.ecr_api.repository_url}:${var.api_image_tag}"

  dynamodb_table_name = module.dynamodb.table_name
  dynamodb_table_arn  = module.dynamodb.table_arn
  dynamodb_gsi_arn    = module.dynamodb.gsi_arn

  sqs_queue_url = module.sqs.queue_url
  sqs_queue_arn = module.sqs.queue_arn

  cognito_user_pool_id = module.cognito.user_pool_id
  cognito_client_id    = module.cognito.client_id
  cognito_issuer       = module.cognito.issuer

  bedrock_model_ids  = local.bedrock_model_ids
  cors_allow_origins = var.cors_allow_origins
}

# --- Worker(Go Lambda + SQS イベントソースマッピング + Bedrock 権限) ---

module "worker" {
  source        = "../../modules/worker"
  function_name = "${local.name_prefix}-worker"
  image_uri     = "${module.ecr_worker.repository_url}:${var.worker_image_tag}"
  timeout       = local.worker_timeout

  sqs_queue_arn = module.sqs.queue_arn

  dynamodb_table_name = module.dynamodb.table_name
  dynamodb_table_arn  = module.dynamodb.table_arn
  dynamodb_gsi_arn    = module.dynamodb.gsi_arn

  bedrock_model_ids = local.bedrock_model_ids
  max_concurrency   = var.worker_max_concurrency
}

# --- Frontend(CloudFront + S3(OAC) + ACM(us-east-1) + Route53) ---

module "frontend" {
  source = "../../modules/frontend"

  providers = {
    aws           = aws
    aws.us_east_1 = aws.us_east_1
  }

  bucket_name          = local.frontend_bucket_name
  domain_name          = local.frontend_domain
  zone_id              = aws_route53_zone.subdomain.zone_id
  dns_delegation_ready = var.dns_delegation_ready
}

# --- Analytics(集計 Lambda + Step Functions + EventBridge Scheduler) ---
# stats アプリ(apps/lambda-stats)実装後に enable_analytics=true で有効化する。
# 既定(false)では stats ECR / Lambda / Step Functions / Scheduler を作らないため、
# イメージ未 push でも全体 apply が成功する。

module "analytics" {
  count           = var.enable_analytics ? 1 : 0
  source          = "../../modules/analytics"
  name_prefix     = local.name_prefix
  stats_image_uri = "${module.ecr_stats[0].repository_url}:${var.stats_image_tag}"

  dynamodb_table_name = module.dynamodb.table_name
  dynamodb_table_arn  = module.dynamodb.table_arn
  dynamodb_gsi_arn    = module.dynamodb.gsi_arn
}
