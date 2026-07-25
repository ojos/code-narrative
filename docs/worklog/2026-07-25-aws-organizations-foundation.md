# 作業ログ: AWS Organizations 基盤整備と code-narrative-prod 作成

- 期間: 2026-07-24 〜 2026-07-25
- 関連 issue: #1
- 詳細 intake: [../intake/2026-07-24-code-narrative-prod-account.md](../intake/2026-07-24-code-narrative-prod-account.md)

新規 AWS 環境を Control Tower ベースのマルチアカウント構成で整備し、外部公開ポートフォリオ `code-narrative` の本番子アカウントをデプロイ可能な状態まで立ち上げた記録。

## 実施タスクと結果

| タスク | 結果 |
|---|---|
| T0 リポジトリ整備 | `ojos/code-narrative`（public）。モノレポ骨子 `apps/{api,lambda-worker,frontend}` + `terraform/` + `.github/workflows/deploy.yml` |
| T0.5 OU 登録 | Workloads / Prod を Control Tower に登録（ベースライン有効化） |
| T1 アカウント発行 | Account Factory で `code-narrative-prod`（`016647419566`）を Prod OU 配下に発行。ido に AdministratorAccess（直接割当）。IAMユーザー0件を確認 |
| T2 コスト統制 | AWS Budgets 20USD（≒3,000円、50/80/100%＋予測超過）+ Cost Anomaly Detection |
| T3 DNS 委任 | Route 53 に `code-narrative.ojos.jp`（zone `Z09250083F726R3CRZ4M7`）を作成。さくら会員メニューに NS 4件を手動登録し `dig NS` で委任確認 |
| T4 Terraform 基盤 | state 用 S3 バケット（`code-narrative-tfstate-016647419566`）+ GitHub OIDC provider + plan/apply 2ロール。state を S3 へ移行、GitHub リポジトリ変数を登録 |
| X1 SCIM 復旧 | 失効していた SCIM アクセストークン（401）を再発行し自動プロビジョニングを復旧 |

## Terraform 構成

- `terraform/bootstrap/` … 子アカウント初期構築（state 基盤・OIDC・plan/apply ロール・Budgets・Cost Anomaly）。ローカル state で手適用 → 自身が作成した S3 バケットへ移行。
- `terraform/environments/prod/` … S3 バックエンド。サブドメイン用 Route 53 ホストゾーン。アプリ基盤（SPEC Phase 2）はここに実装予定。

## 主な判断・ハマりどころ

- **アクセスポータルのログインは Google に `ido@ojos.jp` として認証している必要がある。** 別 Google アカウント（`aizu@bascule.co.jp` 等）や古い AWS セッションが混ざると `app_not_configured_for_user`（IdP 起点）/ `api/execute` 400（SP 起点）になる。設定値（ACS/Entity ID/証明書/NameID）は一貫して正しかった。
- **当該アカウントは USD 請求。** AWS Budgets は JPY 非対応（`supported unit set: [USD]`）のため 20USD 建てに変更。
- **`ojos.jp` は標準の「さくらのDNS」（`ns1/ns2.dns.ne.jp`・会員メニュー）で運用。** Terraform プロバイダ・公開 API が無いため、委任 NS レコードは手動登録。Terraform 対応があるのは別サービスの「さくらのクラウド DNS」のみ。
- **IAM Identity Center インスタンスは Control Tower 管理下。** トラブル時も削除してはいけない（ランディングゾーン破壊リスク）。
- **GWS + SCIM ではグループにユーザーを追加できない**（グループ同期非対応）。当面 ido へ直接割当で運用し、将来必要なら ssosync を検討。

## 今回のスコープ外（別 intake 予定）

1. アプリ基盤の実装（API Gateway + Lambda / DynamoDB / SQS / Cognito / CloudFront+S3 / Bedrock）
2. HTTPS 公開（ACM(us-east-1) + CloudFront + `code-narrative.ojos.jp`）
3. CI/CD の初回稼働確認（PR=plan / main=apply、OIDC ロールの実地検証）
