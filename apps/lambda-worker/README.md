# apps/lambda-worker — SQS Worker (Go / Amazon Bedrock)

SQS をトリガーに起動し、GitHub リポジトリを取得・解析して Amazon Bedrock Converse API でショートショートを生成するワーカー。

- 実行基盤: AWS Lambda（ECR コンテナイメージ / `provided.al2023`）
- 冪等性: `status: queued` のときのみ `processing` へ条件付き更新（ConditionExpression）
- 部分バッチ失敗応答（`ReportBatchItemFailures`）と DLQ を利用

仕様は [../../docs/SPEC.md](../../docs/SPEC.md) §4 ② を参照。

## パッケージ構成

| パッケージ | 責務 |
|---|---|
| `internal/model` | 各機能で共有するドメイン型（外部依存なし） |
| `internal/logging` | `job_id` を必ず含む構造化 JSON ログ |
| `internal/ghclient` | GitHub tarball 取得 / コミットログ取得 / `repo_url` 解析 |
| `internal/extract` | tarball 展開（200MB 上限）と物語素材抽出（100KB 上限） |
| `internal/bedrock` | model_id ホワイトリスト検証 + Converse 呼び出し |
| `internal/store` | DynamoDB への status 遷移書き込み |
| `internal/worker` | 取得→抽出→生成→永続化のオーケストレーションと SQS ハンドラ |
| `main.go` | 依存の結線と `lambda.Start` |

外部 I/O（GitHub / Bedrock / DynamoDB）はすべてインターフェイス経由で注入し、単体テストは実 AWS / ネットワークに接続しない。

## 環境変数

| 変数 | 必須 | 説明 |
|---|---|---|
| `DYNAMODB_TABLE` | 必須 | ジョブレコードを格納する DynamoDB テーブル名 |
| `AWS_REGION` | 必須 | AWS SDK が解決するリージョン（Lambda ランタイムが自動設定） |
| `GITHUB_TOKEN` | 任意 | 設定時は GitHub API のレート制限を 60→5,000 回/時へ引き上げ |

## 開発

```sh
cd apps/lambda-worker
go test ./...
go vet ./...
```
