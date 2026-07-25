# terraform

`code-narrative-prod` 子アカウント内のインフラを管理する。VPC を構築しないフルサーバーレス構成。

## スタック構成

| スタック | 実行者 | state | 内容 |
|---|---|---|---|
| `bootstrap/` | 管理者（Identity Center 経由で手適用） | ローカル → 自身が作成した S3 バケットへ移行 | Terraform state 基盤、GitHub OIDC、plan/apply ロール、Budgets、Cost Anomaly Detection |
| `environments/prod/` | CI/CD（GitHub Actions OIDC） | S3 バックエンド | Route 53 ホストゾーン、およびアプリ基盤一式（SPEC Phase 2） |

`bootstrap/` が先。ここで作られる state バケットと OIDC ロールを前提に `environments/prod/` が動く。

## モジュール構成（`terraform/modules/`）

`environments/prod/main.tf` から責務ごとに以下のモジュールを呼び出す（1 モジュール 1 責務）。

| モジュール | 内容 |
|---|---|
| `ecr/` | ECR リポジトリ（単一）。API / Worker / Stats 用に 3 回呼び出す |
| `dynamodb/` | `CodeNarratives` テーブル（オンデマンド・暗号化・GSI `user_id-created_at-index`） |
| `sqs/` | 標準キュー + DLQ（`maxReceiveCount`）+ DLQ 滞留 CloudWatch アラーム |
| `cognito/` | User Pool + 公開クライアント（Authorization Code + PKCE）+ Hosted UI ドメイン |
| `api/` | Python Lambda（コンテナ）+ API Gateway HTTP API + JWT Authorizer + プロキシ統合 |
| `worker/` | Go Lambda（コンテナ）+ SQS イベントソースマッピング（`maxConcurrency`）+ Bedrock 権限 |
| `frontend/` | S3（OAC）+ CloudFront + ACM（us-east-1 エイリアスプロバイダ）+ A/AAAA レコード |
| `analytics/` | 集計 Lambda + Step Functions（Scan➔集計➔書込）+ EventBridge Scheduler（日次） |

## ECR 先行作成と初回 apply の順序

Lambda はコンテナイメージ（ECR）を参照するが、初回 apply 時点ではイメージが未 push のため、
そのままでは Lambda 作成に失敗する。CI（`deploy.yml`）は次の順序で適用する。

1. **ECR リポジトリを先行作成**: `terraform apply -target=module.ecr_api -target=module.ecr_worker -target=module.ecr_stats`
2. **イメージを build & push**（`:latest` などのタグ）
3. **全体を apply**: Lambda が push 済みイメージを参照して作成される

以降のコードデプロイは CI が `aws lambda update-function-code` でイメージを直接差し替える。
各 Lambda モジュールは `lifecycle { ignore_changes = [image_uri] }` を持ち、この out-of-band 更新を
ドリフトとして検知しない（インフラ管理とコードデプロイの責務分離）。

> 集計 Lambda（`analytics`）のアプリ本体は別タスクで実装・push する前提。本スタックは
> インフラ（関数・ロール・状態機械・スケジュール）のみを構築する。

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

親ゾーン `ojos.jp` への NS 委任が「apply 後にさくら会員メニューで手動登録」運用のため、
**二段階 apply** で行う（委任前のフル apply は ACM の DNS 検証がタイムアウトして失敗するため）。

```bash
cd terraform/environments/prod
terraform init -backend-config=backend.hcl   # backend.hcl.example を複製して作成

# 段階1: NS 委任前。dns_delegation_ready=false(既定)で apply。
#   ACM 検証待機・独自ドメイン配信・A/AAAA は作られず、CloudFront は
#   *.cloudfront.net の暫定配信。ゾーンと name_servers 出力は得られる。
terraform apply

# 段階2: 委任を実施。
terraform output name_servers   # 得た NS 4 件をさくら会員メニューで親 ojos.jp に登録
#   → 委任反映後に独自ドメイン配信を完成させる。
terraform apply -var="dns_delegation_ready=true"
```

`dns_delegation_ready=false`（段階1）で作成されるもの / されないもの:

- 作成される: Route53 委任ゾーン、ECR、DynamoDB、SQS(+DLQ アラーム+SNS)、Cognito、
  API Gateway(+Lambda)、Worker、Step Functions/Scheduler、S3、CloudFront（デフォルト証明書・独自ドメインなし）、ACM 証明書リソースと検証用 DNS レコード（発行はするが検証は未完了）
- 作成されない: `aws_acm_certificate_validation`（検証待機）、CloudFront の独自ドメイン紐付け（ACM 証明書・エイリアス）、`code-narrative.ojos.jp` の A/AAAA レコード

## 認証方針

- 人（bootstrap 適用）: IAM Identity Center の一時クレデンシャル
- CI/CD（prod 適用）: GitHub OIDC。plan は PR ブランチ、apply は main ブランチのみ。長期アクセスキーは一切使わない。
