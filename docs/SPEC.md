# 📋 SPEC.md: code-narrative

## 1. プロジェクト概要

- **プロジェクト名**: `code-narrative`
- **コンセプト**: 指定された GitHub リポジトリ（public）の構造（ディレクトリ構成、主要ソースコード、README、コミット履歴等）を解釈し、Amazon Bedrock を用いて多様な世界観のショートショート（小説）へ非同期変換する AI プラットフォーム
- **目的**:
  1. 高負荷・非同期処理（SQS + Go Lambda）を考慮したマイクロサービス基盤の実証
  2. Amazon Bedrock (Converse API) を活用した複数 LLM モデルの動的切り替え＆プロンプトエンジニアリングの実装
  3. Cognito による認証および CloudFront + S3 による静的ホスティング基盤の実装
  4. Terraform によるインフラ一式（IaC）および GitHub Actions によるモノレポ CI/CD の自動化
- **リポジトリ構造**: モノレポ（Mono-repository）
- **スコープ外（将来拡張）**:
  - Private / 組織リポジトリ対応（GitHub App / PAT によるトークン管理が必要になるため本フェーズでは対象外）
  - Map-Reduce 型の多段要約による大規模リポジトリの深掘り

---

## 2. システムアーキテクチャ & データフロー

```text
 [ユーザー / 管理画面 (CloudFront + S3)]
       │
       ├─ (1. Cognito Hosted UI で認証 / JWT トークン取得)
       │      ※ Authorization Code Grant + PKCE
       ▼
 [2. API Gateway (HTTP API)]
       │
       ├─ (JWT Authorizer で Cognito トークン検証)
       │
       └─ (Lambda プロキシ統合)
              │
              ▼
 [3. REST API (Python/FastAPI + Mangum / AWS Lambda)]
       │
       ├─ (4. DynamoDB へ status=queued の初期レコード書き込み)
       │
       └─ (5. SQS へリクエスト投入 ➔ 202 Accepted 即時返却)
                │
                ▼
      [6. AWS SQS (標準キュー + DLQ)]
                │
                │ (トリガー起動)
                ▼
      [7. Go Lambda Worker (コンテナ)]
                │
                ├─ (8. GitHub からリポジトリ取得)
                │      ・tarball ダウンロード（codeload）
                │      ・コミットログ取得（GitHub REST API）
                │
                ├─ (9. Amazon Bedrock Converse API 呼び出し)
                │      ※ リクエスト指定のモデルをホワイトリスト検証の上、動的駆動
                │
                └─ (10. 生成されたショートショート・メタデータを格納)
                       │
                       ▼
            [11. Amazon DynamoDB]
                       ▲
                       │
 [12. EventBridge Scheduler (日次)] ─➔ [AWS Step Functions (集計バッチ)]
```

---

## 3. モノレポ ディレクトリ構造

```text
code-narrative/
├── .github/
│   ├── workflows/
│   │   ├── deploy.yml           # モノレポ一括 CI/CD パイプライン(PR: plan / main: apply)
│   │   ├── identity-guard.yml   # コミット identity の検証ゲート
│   │   └── copilot-review.yml   # リモート最終レビューゲート
│   └── project-ai-rules.md      # プロジェクト共通の AI 運用ルール
├── apps/
│   ├── api/                     # REST API (Python / FastAPI + Mangum / Lambda コンテナ)
│   │   ├── app/
│   │   │   ├── routers/         # エンドポイント定義
│   │   │   ├── services/        # ジョブ投入・SQS エンキュー
│   │   │   ├── repositories/    # DynamoDB アクセス
│   │   │   └── utils/
│   │   ├── tests/               # pytest
│   │   ├── Dockerfile
│   │   └── pyproject.toml       # 依存は uv 管理(uv.lock を唯一の真実とする)
│   ├── lambda-worker/           # SQS Worker (Go / Amazon Bedrock SDK)
│   │   ├── main.go
│   │   ├── internal/
│   │   │   ├── worker/          # ハンドラ(冪等性・部分バッチ失敗応答)
│   │   │   ├── ghclient/        # tarball / コミット履歴の取得
│   │   │   ├── extract/         # 物語素材の抽出(ツリー・主要ファイル選定)
│   │   │   ├── bedrock/         # Converse API 呼び出し・モデルホワイトリスト
│   │   │   └── store/           # DynamoDB アクセス
│   │   ├── Dockerfile
│   │   └── go.mod
│   ├── lambda-stats/            # 集計バッチ (Go / Step Functions タスク)
│   │   ├── main.go
│   │   ├── internal/
│   │   │   ├── stats/           # 集計ロジック(モデル別利用・プロンプト傾向・トークン)
│   │   │   └── store/           # Scan / STATS# レコード書き込み
│   │   ├── Dockerfile
│   │   └── go.mod
│   └── frontend/                # 管理画面 (CloudFront + S3 静的Web)
│       ├── index.html           # 画面骨格(config.js → js/app.js の順に読み込む)
│       ├── styles.css
│       ├── config.example.js    # 実行時設定の雛形(実値はコミットしない)
│       ├── js/                  # app / auth / pkce / api / models / validation / ui
│       ├── scripts/             # build.js(dist 生成) / check.js(構文チェック)
│       ├── test/                # node:test
│       └── package.json
├── docs/
│   ├── SPEC.md                  # 本仕様書
│   ├── intake/                  # intake 記録
│   └── worklog/                 # 作業ログ
├── scripts/                     # 受け入れ検証(verify/acceptance)・レビューゲート・環境構築
├── .ai-playbook/                # AI エージェント運用の規範
└── terraform/                   # IaC (Terraform)
    ├── bootstrap/               # 子アカウント初期構築(state 基盤・OIDC・コスト統制)。手適用
    ├── environments/
    │   └── prod/                # アプリ基盤一式(S3 バックエンド)。CI/CD から適用
    └── modules/                 # ecr / dynamodb / sqs / cognito / api / worker /
                                 # frontend / analytics(1 モジュール 1 責務)
```

---

## 4. コンポーネント別詳細仕様

### ① REST API (Python / FastAPI + Mangum / AWS Lambda)

- **概要**: ユーザーからのリポジトリ変換リクエストを受領し、初期レコードを記録して SQS へ投入するレシーバー API
- **実行基盤**: API Gateway (HTTP API) の Lambda プロキシ統合。FastAPI を Mangum アダプタ経由で Lambda 上に載せる（ECR のコンテナイメージから起動）
  - VPC には所属させない。DynamoDB / SQS へは IAM 認証によるパブリックエンドポイント経由でアクセスする
  - コールドスタートは実証規模において許容範囲とする
- **エンドポイント**:
  - `POST /api/v1/narratives`: 変換ジョブの投入
    - **Header**: `Authorization: Bearer <Cognito_JWT_Token>`
    - **Request Body**:

      ```json
      {
        "repo_url": "string (例: https://github.com/owner/repo)",
        "custom_prompt": "string (例: SF風のハードボイルドにして)",
        "model_id": "string (許可モデルホワイトリスト内の ID)"
      }
      ```

    - **バリデーション**:
      - `repo_url` は `https://github.com/{owner}/{repo}` 形式のみ許可（public リポジトリ前提）
      - `model_id` は後述の許可モデルホワイトリストと照合し、不一致は `400 Bad Request`
    - **Response** (`202 Accepted`):

      ```json
      {
        "job_id": "uuid-v4-string",
        "status": "queued"
      }
      ```

  - `GET /api/v1/narratives/{job_id}`: 結果取得 API（DynamoDB を参照）
    - 所有者検証: JWT の `sub` とレコードの `user_id` を照合し、不一致は `404 Not Found`
    - **Response** (処理中):

      ```json
      {
        "job_id": "uuid-v4-string",
        "repo_url": "https://github.com/owner/repo",
        "status": "processing",
        "created_at": "2026-07-23T00:00:00Z"
      }
      ```

    - **Response** (完了時):

      ```json
      {
        "job_id": "uuid-v4-string",
        "repo_url": "https://github.com/owner/repo",
        "status": "completed",
        "model_id": "jp.anthropic.claude-sonnet-4-5-20250929-v1:0",
        "generated_story": "string (生成されたショートショート)",
        "created_at": "2026-07-23T00:00:00Z",
        "updated_at": "2026-07-23T00:01:30Z"
      }
      ```

      ※ `status: failed` の場合は `generated_story` の代わりに `error_message` を返却
  - `GET /api/v1/narratives`: 自分のジョブ一覧取得 API
    - GSI（`user_id` + `created_at`）を用いて認証ユーザー自身のジョブを新しい順に返却
    - クエリパラメータ: `limit`（既定 20）、`next_token`（ページネーション）
- **仕様**:
  - API Gateway (HTTP API) の JWT Authorizer で Cognito トークンを検証済みの前提で動作（多層防御として API 側でも署名検証を行ってよい）
  - ジョブ投入時の処理順序:
    1. `job_id` (UUID v4) を採番
    2. DynamoDB へ `status: queued` の初期レコードを書き込み（`user_id` は JWT の `sub`）
    3. SQS へエンキューし `202 Accepted` を返却

### ② SQS & Worker (Go / Lambda コンテナ)

- **概要**: SQS をトリガーに起動し、GitHub リポジトリを取得・解析して Amazon Bedrock でショートショートを生成するワーカー
- **使用ライブラリ**: `github.com/aws/aws-sdk-go-v2/service/bedrockruntime`
- **処理フロー**:
  1. SQS メッセージから `job_id`, `repo_url`, `custom_prompt`, `model_id` を抽出
  2. DynamoDB の該当レコードを `status: processing` へ条件付き更新（冪等性担保。詳細は後述）
  3. **リポジトリ取得**:
     - tarball を `https://codeload.github.com/{owner}/{repo}/tar.gz/HEAD` からダウンロードし、Lambda の `/tmp` に展開
     - コミットログは GitHub REST API `GET /repos/{owner}/{repo}/commits`（直近 30 件: メッセージ・日時・作者）で取得
     - ※ 未認証の GitHub API はレート制限 60 回/時。実証規模では許容とするが、必要に応じて `GITHUB_TOKEN`（5,000 回/時）を Secrets 経由で注入可能な設計とする
  4. **物語素材の抽出**（ツリー + 主要ファイル + コミットログ方式）:
     - ディレクトリツリー（全ファイルパス一覧）を生成
     - README を取得
     - ヒューリスティック（ファイルサイズ・拡張子・エントリポイント推定: `main.*`, `index.*`, `app.*` 等）で主要ソースファイルを数個選定
     - 上記 + コミットログを合計 **100KB を上限**に詰めてプロンプトを構築
  5. **Bedrock Converse API (`ConverseInput`)** を使用し、指定された `model_id` へ以下のシステムプロンプトと共にリクエストを送信（1 回の呼び出しで生成）:

     ```text
     【System Prompt】
     あなたはIT技術と文学に精通した小説家です。
     渡された GitHub リポジトリの情報（ディレクトリ構成、README、主要ソースコード、
     コミット履歴）からプロジェクトの目的・構造・歩みを解釈し、それらをメタファーとして
     用いた魅力的なショートショート（500文字程度）を作成してください。

     【User Request】
     ・ディレクトリツリー:
     {{ directory_tree }}
     ・README:
     {{ readme }}
     ・主要ソースコード:
     {{ selected_files }}
     ・コミット履歴:
     {{ commit_log }}
     ・世界観・スタイル指定:
     {{ custom_prompt }}
     ```

  6. 生成された小説テキスト、抽出要旨、使用モデル、トークン使用量等を **DynamoDB** に書き込み（`status: completed`）
- **サイズ制限**:
  - tarball 展開後のサイズが **200MB を超える**場合は処理を中止し `status: failed`（`error_message` に理由を記録）
  - LLM への抽出コンテンツは合計 **100KB を上限**とする
  - DynamoDB には抽出結果の**要旨（ディレクトリツリー + 選定ファイル名一覧）のみ**を保存し、ファイル全文は保存しない
- **信頼性設計**:
  - **冪等性**: SQS 標準キューは at-least-once 配信のため、`status: queued` の場合のみ `processing` へ遷移させる条件付き書き込み（ConditionExpression）で二重処理を防止
  - **部分バッチ失敗応答**: `ReportBatchItemFailures` を有効化し、失敗メッセージのみ再配信
  - **同時実行制御**: イベントソースマッピングの `maxConcurrency` で Bedrock のスロットリングを回避
  - **エラー記録**: 失敗時は `status: failed` とし `error_message` 属性に原因を記録。SQS の `maxReceiveCount` 超過分は DLQ へ
  - 可視性タイムアウトは Lambda タイムアウトの 6 倍以上を設定
- **Bedrock 呼び出しパラメータ（既定値）**:
  - `maxTokens`: 2048（コスト制御のための上限）
  - `temperature`: 0.8（創作用途のため高め）

### ③ データベース (DynamoDB)

- **テーブル名**: `CodeNarratives`
- **プライマリキー**: `job_id` (String / Hash)
- **GSI**: `user_id-created_at-index`（Hash: `user_id`, Range: `created_at`）— ユーザー別ジョブ一覧用
- **属性構造（変換ジョブレコード）**:
  - `job_id` (String / UUID v4)
  - `user_id` (String / Cognito の `sub`)
  - `repo_url` (String)
  - `status` (String: `queued` / `processing` / `completed` / `failed`)
  - `model_id` (String)
  - `repo_digest` (String / 抽出要旨: ディレクトリツリー + 選定ファイル名一覧)
  - `custom_prompt` (String)
  - `generated_story` (String / 生成された小説)
  - `error_message` (String / 失敗時のみ)
  - `usage` (Map / Bedrock の入出力トークン数)
  - `created_at` (String / ISO8601)
  - `updated_at` (String / ISO8601)
- **集計レコード**: 集計バッチの結果は同一テーブルに `job_id = "STATS#<date>#<metric>"` 形式のキーで格納（例: `STATS#2026-07-23#model_usage`）

### ④ バッチ分析パイプライン (EventBridge Scheduler + AWS Step Functions)

- **概要**: 蓄積されたデータの集計バッチ
- **起動トリガー**: EventBridge Scheduler による日次実行（管理画面からの手動キックも可）
- **ステートマシン構成**: Lambda タスクによる「Scan ➔ 集計 ➔ 書き込み」の直列フロー
  - DynamoDB をスキャンし「モデル別の利用割合」「人気のあるカスタムプロンプト傾向」「トークン使用量合計」を集計
  - 集計結果を `STATS#` プレフィックスのレコードとして同一テーブルへ書き込み
  - ※ 実証規模（データ量小）のため Scan コストは許容範囲とする

### ⑤ フロントエンド & 認証 (CloudFront + S3 + Cognito)

- **配信**: CloudFront + S3（OAC による直接アクセス制御）
- **認証**: AWS Cognito User Pool & Hosted UI
  - 認可フローは **Authorization Code Grant + PKCE** を使用（Implicit フローは非推奨のため不使用）
- **主要機能**:
  1. **ログイン/ログアウト**: Hosted UI リダイレクトによる JWT トークン取得・保持
  2. **変換リクエストフォーム**:
     - GitHub リポジトリ URL 入力欄（public リポジトリのみ）
     - カスタムプロンプト入力欄（「サイバーパンク風」「太宰治風」などのプリセットボタン付き）
     - **Bedrock モデル選択ドロップダウン**（許可モデルホワイトリスト）:
       - `Claude Sonnet 4.5` (`jp.anthropic.claude-sonnet-4-5-20250929-v1:0`) — Anthropic
       - `Amazon Nova Lite` (`amazon.nova-lite-v1:0`) — Amazon
       - `DeepSeek V3.2` (`deepseek.v3.2`) — DeepSeek
       - `Qwen3 32B` (`qwen.qwen3-32b-v1:0`) — Qwen
       - `Gemma 3 12B IT` (`google.gemma-3-12b-it`) — Google
       - ※ 作風の振れ幅を確保するため、ベンダーを重複させず 5 社から 1 モデルずつ選定する
       - ※ 作風の振れ幅は §4② の `temperature` で作るため、Converse の `inferenceConfig.temperature` に対応するモデルに限定する。Claude Sonnet 5 / Opus 4.7 以降は `temperature` / `top_p` / `top_k` を送ると 400 になるため対象外（採用する場合は多様性をプロンプト側で作る設計変更が前提）
       - ※ デプロイ先 ap-northeast-1（東京）では Claude は `jp.` 地域推論プロファイル ID が必須（`us.` / `global.` は不可）。Llama 3.3 70B は東京で推論プロファイル提供がないため除外
       - ※ 実装時に利用リージョンでの各モデルの提供状況を確認すること。モデル ID は AWS の model card ページの Programmatic Access 表を正とする（地域一覧ページの要約と食い違うことがある）
     - **入力の永続化**: 上記 3 入力（リポジトリ URL / カスタムプロンプト / モデル選択）を `localStorage` の `cn.form.draft` に保持し、リロードや Hosted UI からのリダイレクト復帰でも同じ入力状態を復元する
       - 同じリポジトリを別モデル・別作風で繰り返し変換して比較する利用形態を前提とする
       - **ログアウト時に破棄する**。共用ブラウザで次の利用者に前の利用者のリポジトリ URL が残らないようにする
       - 復元時に値を検証する。ホワイトリスト外のモデル ID は既定モデルへフォールバックし、カスタムプロンプトは §4① の上限（2000 文字）で切り詰める。ホワイトリストは保存後に変わりうるため、検証は書き込み時ではなく読み出し時に行う
       - 認証トークンは対象外（`sessionStorage` の `cn.auth.*` に保持する。キー空間を分ける）
       - `localStorage` が利用できない環境では、保存・復元のみを無効化しフォーム本体の動作は維持する
  3. **結果表示エリア**: ポーリングまたは結果取得 API により、生成されたショートショートを表示
  4. **履歴一覧**: ジョブ一覧 API により自分の変換履歴を表示

---

## 5. インフラ設計 (Terraform)

- **ネットワーク**: VPC を構築しない（フルサーバーレス構成）。VPC / NAT Gateway / VPC Link に伴う固定費を排し、各サービスへは IAM 認証によるパブリックエンドポイント経由でアクセスする
- **API Gateway (HTTP API)**: JWT Authorizer（Cognito）+ Lambda プロキシ統合
- **AWS Lambda (Python)**: ECR イメージから起動する REST API（FastAPI + Mangum）
- **AWS Lambda (Go)**: ECR イメージから起動する SQS ワーカー（Bedrock 呼び出し権限保持、イベントソースマッピングに `maxConcurrency` 設定）
- **AWS SQS**: 標準キュー ＋ DLQ（Dead Letter Queue、`maxReceiveCount` 設定）
- **Amazon Bedrock**: IAM Policy にて `bedrock:InvokeModel` を Lambda ロールに付与（許可モデルの推論プロファイル / Foundation Model ARN に限定）
- **Amazon DynamoDB**: オンデマンドモード（暗号化有効）、GSI `user_id-created_at-index`
- **EventBridge Scheduler**: 集計バッチの日次起動
- **AWS Step Functions**: 集計バッチのステートマシン
- **AWS Cognito**: User Pool, User Pool Client（Authorization Code Grant + PKCE）, Hosted UI ドメイン設定
- **CloudFront & S3**: OAC (Origin Access Control) による S3 セキュア配信
- **ECR**: API / Worker それぞれのコンテナレジストリ
- **セキュリティ・鍵管理**:
  - API キー不要（Bedrock 呼び出しはすべて IAM 認証）
  - IAM 最小権限原則の徹底
  - CI/CD からの AWS 認証は GitHub OIDC フェデレーション（長期アクセスキー不使用）
  - OIDC ロールは plan 用（読み取り + state バケット / PR ブランチ）と apply 用（書き込み / main ブランチのみ）に分離する
- **Terraform state**: S3 バックエンド（ロック有効）で管理。バケットおよび OIDC ロールはアカウント初期構築時に手作業で用意し、Terraform の管理対象外とする（ブートストラップ資材）
- **コスト統制**: AWS Budgets（月次しきい値 20 USD ≒ 3,000 円 / 50・80・100% および予測超過で通知。当該アカウントは USD 請求）と Cost Anomaly Detection を有効化

---

## 6. CI/CD パイプライン (GitHub Actions)

`.github/workflows/deploy.yml` にて、パス判定 (Paths Filter) による変更検知を共通の前段とした 2 段構成:

### PR 作成・更新時（検証）

1. **Terraform**: `terraform init` ➔ `terraform plan` を実行し、結果を PR へコメント
2. **Go Lambda / Python API**: コンテナビルド（プッシュなし）・テスト実行

### main へのマージ時（デプロイ）

1. **Terraform**: `terraform apply -auto-approve`（PR で plan レビュー済みの内容を適用。ECR 等の依存リソースを先行作成）
2. **Go Lambda**: コンテナビルド ➔ ECR へプッシュ ➔ Lambda 関数更新
3. **Python API**: コンテナビルド ➔ ECR へプッシュ ➔ Lambda 関数更新
4. **Frontend**: `aws s3 sync` ➔ CloudFront キャッシュ削除 (`invalidation`)

- AWS 認証は **GitHub OIDC** による AssumeRole（シークレットに長期キーを保存しない）
- PR 時は plan 用ロール、main マージ時は apply 用ロールを引く。PR ブランチから apply 用ロールは引けない

---

## 7. 可観測性 (Observability)

- **ログ**: API / Worker ともに構造化ログ（JSON）を CloudWatch Logs へ出力（`job_id` を必ず含め追跡可能にする）
- **アラーム**: DLQ の滞留メッセージ数に対する CloudWatch アラーム（変換失敗の検知）
- **コスト可視化**: Bedrock レスポンスの `usage`（入出力トークン数）を DynamoDB に保存し、集計バッチの分析素材とする

---

## 8. 実装ステップ（Claude Code 指示用フェーズ）

- **Phase 1: アプリ基盤作成**
  - モノレポ構造のセットアップ
  - `apps/api`（FastAPI: 初期レコード書き込み + SQS エンキュー + 結果/一覧取得）の実装
  - `apps/lambda-worker`（Go: tarball 取得 ➔ 素材抽出 ➔ Bedrock Converse API 呼出 ➔ DynamoDB 書き込み）の実装
- **Phase 2: IaC (Terraform) 構築**
  - `terraform/` に API Gateway (HTTP API), Lambda (API / Worker), SQS, DynamoDB (GSI 含む), Cognito, ECR, EventBridge Scheduler, Step Functions, CloudFront + S3, IAM (Bedrock 権限) のモジュールコードを作成
  - S3 state バックエンドの設定（バケットと OIDC ロールはアカウント初期構築で作成済みの前提）
- **Phase 3: フロントエンド & 統合**
  - `apps/frontend/` に Cognito ログイン（PKCE）、リポジトリ URL 入力、モデル選択 UI、履歴一覧を持つ画面を作成し、API との接続疎通を確認
- **Phase 4: CI/CD & ドキュメンテーション**
  - `.github/workflows/deploy.yml`（PR: plan / merge: apply ➔ ビルド ➔ デプロイ）の作成および動作検証
