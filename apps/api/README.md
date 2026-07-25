# apps/api — REST API (Python / FastAPI + Mangum / Lambda)

リポジトリ変換リクエストを受領し、DynamoDB へ初期レコードを書き込み、SQS へ投入するレシーバー API。

- 実行基盤: API Gateway (HTTP API) の Lambda プロキシ統合（ECR コンテナイメージ）
- VPC 非所属。DynamoDB / SQS へは IAM 認証によるパブリックエンドポイント経由
- 認証: API Gateway の JWT Authorizer（Cognito）で検証済み前提

仕様は [../../docs/SPEC.md](../../docs/SPEC.md) §4 ① を参照。実装は Phase 1 で行う。

## 開発

パッケージ管理は [uv](https://docs.astral.sh/uv/) を使用する。依存は `pyproject.toml`（本番）と `dependency-groups.dev`（開発）に定義し、`uv.lock` で固定する。

```bash
# 依存を同期（dev グループ込みで .venv を構築）
uv sync

# テスト
uv run pytest

# 依存を追加/更新（uv.lock も更新される）
uv add <package>            # 本番依存
uv add --dev <package>      # 開発依存
```

Docker イメージは uv でビルドし、実行イメージには uv バイナリを含めない（本番依存のみを `LAMBDA_TASK_ROOT` へ展開）。

```bash
docker build -t code-narrative-api .
```
