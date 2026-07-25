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
| `PROCESSING_LEASE_SECONDS` | 任意 | processing リースの有効期間（既定 900）。可視性タイムアウト相当以上を想定。一時障害で processing のまま取り残されたジョブは、この期間経過後の再配信で再取得される |

## 信頼性メモ

- **processing リース**: `MarkProcessing` は「status=queued、または status=processing かつ updated_at がリース失効（stale）」の条件付き更新で processing を獲得する。これにより、MarkProcessing 成功後に一時障害で再配信されたジョブがリース失効後に再取得され、completed/failed へ確実に遷移する（processing のまま放置＝結果喪失を防止）。同時二重配信は条件付き書込で片方のみ成功し、他方はスキップされる。
- **tarball ダウンロードのタイムアウト**: 取得〜`Untar` の期限は `ctx`（Lambda デッドライン）で制御する。ダウンロード用 HTTP クライアントには `Client.Timeout` を設定しない（本文読了までのハード期限が展開全体に及び、正当な大リポジトリを偽陰性で failed 化するのを避けるため）。コミットログ取得側は 60 秒のタイムアウトを維持。

## 開発

```sh
cd apps/lambda-worker
go test ./...
go vet ./...
```
