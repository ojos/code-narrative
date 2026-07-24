# apps/lambda-worker — SQS Worker (Go / Amazon Bedrock)

SQS をトリガーに起動し、GitHub リポジトリを取得・解析して Amazon Bedrock Converse API でショートショートを生成するワーカー。

- 実行基盤: AWS Lambda（ECR コンテナイメージ）
- 冪等性: `status: queued` のときのみ `processing` へ条件付き更新
- 部分バッチ失敗応答（`ReportBatchItemFailures`）と DLQ を利用

仕様は [../../docs/SPEC.md](../../docs/SPEC.md) §4 ② を参照。実装は Phase 1 で行う。
