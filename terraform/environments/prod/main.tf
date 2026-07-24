# アプリ基盤一式(SPEC Phase 2)はここに実装する。
#
# 予定リソース(docs/SPEC.md §5):
#   - API Gateway (HTTP API) + JWT Authorizer (Cognito)
#   - Lambda (Python API / Go Worker、ECR コンテナイメージ)
#   - SQS(標準キュー + DLQ)
#   - DynamoDB(オンデマンド、GSI user_id-created_at-index)
#   - Cognito User Pool / Client / Hosted UI
#   - CloudFront + S3(OAC)
#   - ACM 証明書(aws.us_east_1 プロバイダーで発行、CloudFront 用)
#   - EventBridge Scheduler + Step Functions(集計バッチ)
#
# 各リソースは terraform/modules/ 配下のモジュールに分割して呼び出す。
