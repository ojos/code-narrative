# terraform

`code-narrative-prod` 子アカウント内のインフラを管理する。VPC を構築しないフルサーバーレス構成。

## スタック構成

| スタック | 実行者 | state | 内容 |
|---|---|---|---|
| `bootstrap/` | 管理者（Identity Center 経由で手適用） | ローカル → 自身が作成した S3 バケットへ移行 | Terraform state 基盤、GitHub OIDC、plan/apply ロール、Budgets、Cost Anomaly Detection |
| `environments/prod/` | CI/CD（GitHub Actions OIDC） | S3 バックエンド | Route 53 ホストゾーン、およびアプリ基盤一式（SPEC Phase 2） |

`bootstrap/` が先。ここで作られる state バケットと OIDC ロールを前提に `environments/prod/` が動く。

## 適用順序

### 1. bootstrap（初回のみ・手作業）

`code-narrative-prod` に Identity Center 経由で `AdministratorAccess` としてログインした状態で実行する。

```bash
cd terraform/bootstrap
cp terraform.tfvars.example terraform.tfvars   # 値を埋める
terraform init            # 初回はローカル state
terraform apply
# 出力された state バケット名で backend を有効化し、state を移行:
terraform init -migrate-state \
  -backend-config="bucket=$(terraform output -raw tfstate_bucket)" \
  -backend-config="key=bootstrap/terraform.tfstate" \
  -backend-config="region=ap-northeast-1" \
  -backend-config="use_lockfile=true"
```

### 2. environments/prod（以降は CI/CD が適用）

```bash
cd terraform/environments/prod
terraform init -backend-config=backend.hcl   # backend.hcl.example を複製して作成
terraform apply
```

`terraform output name_servers` で得た NS レコードを、親ゾーン `ojos.jp` 側に登録してサブドメインを委任する（親ゾーンの管理先は intake の P2 に依存）。

## 認証方針

- 人（bootstrap 適用）: IAM Identity Center の一時クレデンシャル
- CI/CD（prod 適用）: GitHub OIDC。plan は PR ブランチ、apply は main ブランチのみ。長期アクセスキーは一切使わない。
