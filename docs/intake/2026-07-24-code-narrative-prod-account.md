# Intake: code-narrative 本番用 AWS 子アカウント作成

- 起票日: 2026-07-24
- 起票者ロール: intake-manager
- ステータス: **承認済み / 論点解消済み・着手可**
- 起票先: GitHub issue 未作成（ローカル git リポジトリ・リモートリポジトリともに未整備のため本ファイルで代替）

## intake 判定

| 項目 | 値 |
|---|---|
| intake 要否 | 必要 |
| reason_code | `IMPLEMENTATION_MISSING_MULTIPLE` |
| 判定時の不足項目 | `goal` / `acceptance` / `priority` / `scope.out` / `constraints` |
| 充足状況 | Q1〜Q8 の確認により必須項目を充足 |

## intake 票

```yaml
goal: >
  ポートフォリオWebサービス "code-narrative" を外部公開するためのAWS子アカウントを、
  Workloads/Prod OU 配下に統制された状態で新規作成し、
  デプロイ可能な基盤(サブドメイン委任・OIDC連携)まで整備する

scope.in:
  - Account Factory による子アカウント作成
      名称: code-narrative-prod
      ルートメール: aws+code-narrative@ojos.jp
  - 作成した子アカウントを既存の Workloads/Prod OU に配置
  - Identity Center の権限割当整備
      - ido@ojos.jp が AdministratorAccess でアクセスできる状態にする
      - 割当はグループ経由とし、ユーザーへの直接割当を残さない
  - コスト統制
      - AWS Budgets: 月3,000円(50% / 80% / 100% / 予測超過で通知) (R1)
      - Cost Anomaly Detection の有効化
  - DNS 委任
      - 子アカウントに code-narrative.ojos.jp のホストゾーンを作成
      - 親ゾーン側に NS レコードを登録して委任
  - Terraform ブートストラップ資材の作成 (R3)
      - Terraform state 用 S3 バケット(バージョニング + ロック有効)
  - GitHub Actions デプロイ基盤 (R4)
      - OIDC プロバイダー登録
      - plan 用 IAM ロール(読み取り + state バケットアクセス、PR ブランチから)
      - apply 用 IAM ロール(書き込み、main ブランチのみ)
      - 信頼ポリシーを対象リポジトリ・対象ブランチに限定

scope.out:
  - Webサービス本体の実装およびHTTPS公開(ダミーページ含む)
  - ACM証明書発行・CloudFront等の配信基盤構築
  - 開発検証用アカウント(code-narrative-dev)の作成
  - 外部業務提携メンバーのアクセス受け入れ
  - アプリケーションリソースの Terraform 実装
  - Prod OU への SCP 設計・適用(現在 SCP は未設定。別 intake で扱う)

constraints:
  - 外部IdP(GWS)採用のため、Identity Center 内蔵ディレクトリとの併用は不可
  - AWS操作者は ido@ojos.jp のみ。GWS喪失時の唯一の脱出口は
    管理アカウントのルートユーザーであり、その可用性に依存する
  - AWSアカウントのルートメールは既存アカウントと重複不可
  - 既存の Control Tower 既定グループ8個は名前と実態を乖離させない。
    ワークロード用権限が必要な場合は新規グループを1つ追加する
  - Workloads/Prod OU に SCP は未設定。将来 SCP を設計する際は
    Bedrock のクロスリージョン推論(us-*)と CloudFront 用 ACM(us-east-1)を
    ブロックしないリージョン許可設計とすること (R2)

acceptance:
  1. aws organizations list-accounts-for-parent で code-narrative-prod が
     Workloads/Prod OU 配下に存在することを確認できる
  2. ido@ojos.jp がアクセスポータル経由で code-narrative-prod に
     AdministratorAccess でログインできる
  3. 当該アカウントの割当がすべてグループ経由であり、
     ユーザーへの直接割当が 0 件である
  4. Budgets にしきい値が設定され、通知メールの受信を確認済み
  5. Cost Anomaly Detection が有効である
  6. dig NS code-narrative.ojos.jp が子アカウントのホストゾーンの
     ネームサーバーを返す
  7. GitHub Actions の PR ブランチから plan 用ロールへの AssumeRole が成功し、
     aws sts get-caller-identity が想定のロールARNを返す(アクセスキー不使用)
  8. GitHub Actions の main ブランチから apply 用ロールへの AssumeRole が成功する
  9. PR ブランチから apply 用ロールへの AssumeRole が失敗する
 10. 対象外リポジトリからの AssumeRole が plan / apply いずれも失敗する
 11. Terraform state 用 S3 バケットが存在し、バージョニングが有効で、
     plan / apply 両ロールから読み書きできる
 12. 当該アカウントの CloudTrail が有効で、Log Archive へ配信されている
 13. 当該アカウントに IAM ユーザーが 0 件である

priority: high
```

## 確認済みの決定事項

| # | 決定内容 |
|---|---|
| Q1 | 案A（Workloads/Prod OU に配置）。同 OU は既存のため新設作業は不要 |
| Q2 | ルートメールは `aws+code-narrative@ojos.jp`（既存 GWS グループ `aws@ojos.jp` のプラスエイリアス） |
| Q3 | 本番アカウント 1 つのみ。dev アカウントは対象外 |
| Q4 | サブドメイン `code-narrative.ojos.jp` を子アカウントへ委任 |
| Q5 | Budgets しきい値 月3,000円（当初 1,000 円。R1 の SPEC 改訂を受けて確定） |
| Q6 | GitHub Actions + OIDC 基盤を今回のスコープに含める |
| Q7 | 完了定義は基盤の完成まで。HTTPS 公開は含めない |
| Q8 | priority: high |

## 実施タスク順序

| 順 | タスク | 状態 | 備考 |
|---|---|---|---|
| **T0** | **開発リポジトリの整備** | **完了**（2026-07-24） | `ojos/code-narrative`（public）。詳細は下記「T0 詳細」 |
| **T0.5** | **OU の Control Tower 登録（整備）** | **完了**（2026-07-25） | Workloads / Prod のベースラインが有効化済み |
| T1 | 子アカウント作成・OU 配置・Identity Center 割当 | **アカウント発行完了**（2026-07-25） | `code-narrative-prod`（`016647419566`）が Prod OU 配下でエンロール済（統制有効・CTベースライン有効）。残: ido のログイン確認と直接割当の是正 |
| T2 | Budgets / Cost Anomaly Detection | **完了**（2026-07-25） | 月20USD(≒3,000円)。Cost Anomaly 有効。`terraform/bootstrap` apply 済 |
| T3 | Route 53 サブドメイン委任 | 未着手 | AWS 側(子ゾーン)は `terraform/environments/prod` で Terraform 管理。さくら側(親ゾーン NS 登録)は**手動**(標準さくらのDNS は Terraform 非対応) |
| T4 | Terraform state バケット + OIDC 2ロール | **完了**（2026-07-25） | `terraform/bootstrap` apply 済・state を S3(`code-narrative-tfstate-016647419566`)へ移行済。GitHub 変数3つ登録済 |

### T0.5 詳細: OU の Control Tower 登録（整備）

- **背景**: `Sandbox` / `Suspended` / `Workloads` / `Dev` / `Prod` / `Infrastructure` の各 OU は AWS Organizations 上には存在するが、**Control Tower のベースラインが未登録（「有効になっていません」）**。登録済みは Security OU（CT コア）と管理アカウントのみ。
- **影響**: Account Factory は**ベースライン有効な OU にしかアカウントを作れない**ため、Prod がドロップダウンに出ず T1 が着手できない。
- **作業（Control Tower → 組織）**:
  - `Prod` を選択 → アクション → **OU を登録**（ベースライン有効化）。空 OU のため数分。親 Workloads の登録を求められたら Workloads → Prod の順で登録。
  - 将来使う `Dev` も必要に応じて同様に登録（今回は Prod のみで可）。
  - `Sandbox` / `Suspended` / `Infrastructure` は当面未登録のままでよい。
- **完了条件**:
  - Prod の「AWS Control Tower のベースラインステータス」が**有効**になる。
  - Account Factory の OU 選択に Prod が表示される。

Terraform 方針: T1（アカウント発行）は Control Tower Account Factory の一度きりの操作のため手作業とし、T2〜T4 および以降のアプリ基盤（SPEC Phase 2）はすべて Terraform で管理する。適用順序は `terraform/README.md` を参照。

### T0 詳細: 開発リポジトリの整備

- **目的**: 現在ローカル git 未初期化・リモート未作成。SPEC / intake / 今後の IaC・アプリコードの版管理基盤を用意する。
- **作業**:
  - `git init`（デフォルトブランチ `main`）
  - 既存資材（`docs/`, `.ai-playbook/`, `CLAUDE.md` 等）を初期コミット。`.gitignore` の `docs/sso/` 除外が効いていることをコミット前に確認
  - SPEC §3 に沿ったモノレポ骨子ディレクトリの用意（`apps/api`, `apps/lambda-worker`, `apps/frontend`, `terraform/`）
  - GitHub リモートリポジトリ作成と push
- **完了条件（すべて達成）**:
  - `git status` がクリーンで、`docs/sso/` が追跡対象外である ✓
  - リモートの `main` ブランチに初期コミットが存在する ✓（`ojos/code-narrative`）
  - リポジトリ名とデプロイ対象ブランチが確定し、P3 を解消している ✓
- **確定事項**: リポジトリ `ojos/code-narrative`（public）。デプロイ対象ブランチは `main`（apply）/ PR（plan）。
- **成果物**:
  - モノレポ骨子 `apps/{api,lambda-worker,frontend}`
  - Terraform `terraform/{bootstrap,environments/prod,modules}`（`fmt` / `validate` 済）
  - CI/CD `.github/workflows/deploy.yml`（OIDC、PR=plan / main=apply）

## 着手前の事前条件

| # | 内容 | 状態 |
|---|---|---|
| P1 | `aws+code-narrative@ojos.jp` の受信検証 | **解決**（2026-07-24 テスト送信。`aws.ojos.jp` ML 経由で着信確認） |
| P2 | `ojos.jp` の権威 DNS の管理場所と NS レコード追加権限 | **解決**（`ns1/ns2.dns.ne.jp` = 標準さくらのDNS/会員メニュー。Terraform 非対応のため委任 NS は手動登録） |
| P3 | GitHub リポジトリ名とデプロイ対象ブランチ | **解決**（`ojos/code-narrative` / main=apply, PR=plan） |
| P4 | 管理アカウントのルートユーザーの MFA・復旧経路 | 未確認 |

## 別課題（作業中に発見・本 intake とは独立）

| # | 内容 | 状態 |
|---|---|---|
| X1 | **SCIM 自動プロビジョニングが全ユーザーで 401（コード 45003）** | 未対応。Google→Identity Center の SCIM アクセストークンが失効。名前等の属性同期・退職者の自動失効が停止中（セキュリティリスク）。**対処: IAM Identity Center 設定→自動プロビジョニングでトークン再発行→Google 側に差し替え**。SAML ログインとは別系統でログインには影響しない。 |
| X2 | Identity Center のグループにユーザーを追加できない（GWS＋SCIM 制約） | 当面は ido へ**直接割り当て**で運用。将来グループ運用が必要なら ssosync 導入を別 intake 化。 |

## 論点の対応状況（docs/SPEC.md との突き合わせで検出）

承認後に `docs/SPEC.md` を確認した結果、intake の確定値と矛盾する事項が判明した。

| # | 内容 | 状態 |
|---|---|---|
| R1 | Budgets しきい値と構成の不整合 | 解決（SPEC を Lambda 構成へ改訂し、しきい値を月 3,000 円で確定） |
| R2 | リージョン制限 SCP と Bedrock / ACM の衝突 | 解決（Prod OU に SCP 未設定。将来の設計制約として `constraints` へ記録） |
| R3 | Terraform ブートストラップ資材の漏れ | 解決（state 用 S3 バケットを `scope.in` へ追加） |
| R4 | OIDC ロールの plan / apply 分離 | 解決（2 ロール構成へ変更し acceptance 7〜11 を拡張） |
| R5 | `docs/sso/` の機密情報 | 解決（`.gitignore` に `docs/sso/` を追加） |

### R1: Budgets しきい値 月1,000円が構成と整合しない（解決済み）

SPEC の構成（VPC + プライベートサブネット + ECS Fargate 常時稼働 + API Gateway VPC Link + NAT + CloudFront + Cognito + DynamoDB + Bedrock）では、固定費だけで月 1,000 円を大きく超過する。

概算（東京リージョン・月額）:

| 項目 | 概算 |
|---|---|
| NAT Gateway（時間課金のみ） | 約 5,000 円 |
| ECS Fargate 0.25vCPU/0.5GB 常時 1 タスク | 約 1,400 円 |
| Route 53 ホストゾーン | 約 75 円 |
| Bedrock / CloudFront / DynamoDB 等 | 従量 |

しきい値 1,000 円では常時アラートが鳴り続け、通知が機能しなくなる。

**対応**: `docs/SPEC.md` を改訂し、REST API を ECS Fargate から API Gateway + Lambda（FastAPI + Mangum）へ変更した。VPC / VPC Link / NAT Gateway が不要となり、固定費は約 6,500 円/月から約 100 円/月（Route 53 ホストゾーン相当）へ低減する。以降の主たる変動費は Bedrock の従量課金となる。

これを踏まえ、**Budgets しきい値を月 3,000 円で確定**する（50 / 80 / 100% および予測超過で通知）。

### R2: リージョン制限 SCP と Bedrock / ACM が衝突する（解決済み）

- SPEC 内の注記のとおり、Anthropic 系モデルはクロスリージョン推論プロファイル（`us.` プレフィックス）での呼び出しが必須であり、米国リージョンへの推論リクエストが発生する
- CloudFront 用の ACM 証明書は us-east-1 でのみ発行可能

確認の結果、Workloads/Prod OU は存在するのみで **SCP は未設定**であり、現時点の衝突はない。将来 SCP を設計する際の制約として `constraints` へ記録した。

### R3: Terraform ブートストラップ資材が scope.in から漏れている（解決済み）

SPEC ではインフラ一式を Terraform で構築し、state は S3 バックエンド（ロック有効）で管理する方針。手作業と Terraform 管理の境界を次のとおり定義し、`scope.in` を訂正した。

- 今回（コンソール / Account Factory）: アカウント作成、OU 配置、Identity Center 割当、Budgets、Route 53 ホストゾーンと NS 委任、OIDC プロバイダー、plan / apply ロール、**Terraform state 用 S3 バケット**
- 別 intake（Terraform）: アカウント内のアプリケーションリソース一式

### R4: OIDC ロールを plan 用と apply 用に分離すべき（解決済み）

SPEC の CI/CD は PR で `terraform plan`、main で `terraform apply -auto-approve` を実行する。apply 用ロールは IAM 作成権限を含むほぼ管理者相当の権限となるため、次の 2 ロール構成へ訂正した。

- plan 用: 読み取り専用 + state バケットへのアクセス。PR ブランチから AssumeRole 可
- apply 用: 書き込み権限。main ブランチのみ AssumeRole 可

acceptance 7〜11 を 2 ロール分の検証へ拡張済み。

### R5: `docs/sso/` 配下の機密情報の取り扱い（解決済み）

`.gitignore` に `docs/sso/` を追加し、追跡対象外とした。

なお `gws.txt` / `aws.txt` を確認したところ、`token` / `secret` / `password` 等のキーワードは含まれていなかった。ただし SAML 署名証明書と IdP 接続情報を含むディレクトリであるため、ディレクトリ単位で除外している。

## 関連

- 仕様書: [SPEC.md](../SPEC.md)
- テンプレート: [intake-template](../../.ai-playbook/intake/intake-template.md)
- ロール契約: [intake-manager](../../.ai-playbook/role-contracts/intake-manager.md)
- 判定根拠: [REASON_CODES](../../.ai-playbook/intake/REASON_CODES.md)
