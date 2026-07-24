# apps/api — REST API (Python / FastAPI + Mangum / Lambda)

リポジトリ変換リクエストを受領し、DynamoDB へ初期レコードを書き込み、SQS へ投入するレシーバー API。

- 実行基盤: API Gateway (HTTP API) の Lambda プロキシ統合（ECR コンテナイメージ）
- VPC 非所属。DynamoDB / SQS へは IAM 認証によるパブリックエンドポイント経由
- 認証: API Gateway の JWT Authorizer（Cognito）で検証済み前提

仕様は [../../docs/SPEC.md](../../docs/SPEC.md) §4 ① を参照。実装は Phase 1 で行う。
