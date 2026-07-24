# code-narrative

指定された public な GitHub リポジトリの構造（ディレクトリ構成・主要ソース・README・コミット履歴）を解釈し、Amazon Bedrock で多様な世界観のショートショートへ非同期変換する AI プラットフォーム。

詳細な設計は [docs/SPEC.md](docs/SPEC.md) を参照。

## リポジトリ構成（モノレポ）

```
code-narrative/
├── apps/
│   ├── api/            # REST API (Python / FastAPI + Mangum / Lambda)
│   ├── lambda-worker/  # SQS Worker (Go / Amazon Bedrock)
│   └── frontend/       # 管理画面 (CloudFront + S3 静的Web)
├── terraform/          # IaC
│   ├── bootstrap/      # 子アカウント初期構築(state基盤・OIDC・コスト統制)。ローカルstateで手適用
│   ├── environments/
│   │   └── prod/       # アプリ基盤一式(S3バックエンド)。CI/CD から適用
│   └── modules/        # 再利用モジュール
├── docs/               # 仕様・intake 記録
└── .github/workflows/  # CI/CD (plan on PR / apply on main)
```

## インフラ構成方針

- **フルサーバーレス**（VPC を構築しない）。REST API は API Gateway + Lambda、非同期処理は SQS + Go Lambda。
- **アカウント分離**: 本サービスは AWS Organizations の専用子アカウント `code-narrative-prod`（Workloads/Prod OU）で稼働。
- **認証**: 人は IAM Identity Center、CI/CD は GitHub OIDC フェデレーション（長期アクセスキー不使用）。

## セットアップ順序

`terraform/README.md` を参照。bootstrap（手適用）→ prod（CI/CD 適用）の順。
