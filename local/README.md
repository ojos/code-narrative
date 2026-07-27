# ローカル実行環境

本番の非同期パス（API → DynamoDB → SQS → Worker → Bedrock → DynamoDB）を
docker-compose で再現し、**実 AWS リソースを一切使わずに非対話で完走する統合テスト**を
提供します（issue #74）。

> このディレクトリの資材はローカル検証専用です。Lambda のイメージにも Terraform の
> 管理対象にも含まれません。

## 使い方

**VS Code でこのワークスペースを devcontainer として開くと、アプリのコンテナも一緒に
起動します。**`devcontainer.json` が `compose.yaml`（開発コンテナ）と
`compose.app.yaml`（アプリ）を合成しているためです。手で起動・破棄する場合は次のとおり。

```bash
# 起動（初回はイメージのビルドが走ります）
docker compose -f .devcontainer/compose.app.yaml up -d --wait

# 統合テスト（非対話・終了コードで合否）
bash scripts/integration-test.sh

# 画面を開く（ホスト側のブラウザから）
open http://localhost:8080

# 破棄（devcontainer の中からは down ではなく stop + rm。理由は後述）
docker compose -f .devcontainer/compose.app.yaml stop
docker compose -f .devcontainer/compose.app.yaml rm -f -v
```

`scripts/verify.sh` からも同じ統合テストが実行されます（`scripts/acceptance.sh` 経由）。
docker が使えない環境では自動でスキップします。

### compose ファイルが 2 つあります

| ファイル | 責務 |
|---|---|
| `.devcontainer/compose.yaml` | 開発コンテナ（`app`）を起動する |
| `.devcontainer/compose.app.yaml` | アプリ本体のローカル実行環境を起動する |

`devcontainer.json` が両方を `dockerComposeFile` に並べているので、**`app` とアプリ各
サービスは同じ compose プロジェクト・同じネットワークに入ります**。その結果、
devcontainer の中から publish 済みポートを介さずにサービス名で直接叩けます。

```bash
curl http://apigw:8080/health   # devcontainer の中から通る
```

これは前提として重要です。この devcontainer は docker-outside-of-docker 構成のため、
`ports:` で publish したポートは**ホスト側にしか現れず、devcontainer からは見えません**。
ネットワークを共有していなければ、コンテナの中からしかアプリに触れません。

プロジェクト名は `compose.app.yaml` の top-level `name:`（`code-narrative-local`）です。
**この指定は devcontainer 経由でも効きます**（VS Code は `-p` で上書きしません）。素の
ホストから叩いても同じ名前に落ちるため、`-p` を付けなくても同じサービスのもう一組が
別プロジェクトとして立ち上がることはありません。`scripts/integration-test.sh` は自分の
コンテナのラベルからプロジェクト名を解決するので、どちらの経路でも一致します。

> **devcontainer 内から `down` は使わないでください。** プロジェクトを `app` と共有して
> いるため、`down` はコンテナを消したあとネットワークの削除で失敗します（`app` が
> 繋がったままなので落とせません）。上記のとおり `stop` + `rm -f -v` を使います。

> **`-f` に `compose.yaml` を足して `down -v` しないでください。** 開発コンテナ側の
> 永続化ボリューム（認証状態・Claude Code の履歴）まで削除されます。

`compose.yaml` の永続化ボリュームには実体名を明示しています（`name:`）。明示しないと
実体名が「プロジェクト名 + ボリューム名」になり、プロジェクト名を変えた瞬間に空の
ボリュームへ切り替わって認証状態と作業履歴が失われるためです（#78）。

> **アプリを一緒に起動したくない場合**は `devcontainer.json` に
> `"runServices": ["app"]` を足してください。devcontainer のリビルド時間も短くなります。

## 構成

| サービス | 実体 | 本番での対応 |
|---|---|---|
| `api` | `apps/api` の**本番と同一イメージ** + Lambda RIE | Lambda（コンテナ） |
| `worker` | `apps/lambda-worker` の**本番と同一イメージ** + Lambda RIE | Lambda（コンテナ） |
| `apigw` | `local/emulator/apigw.py` | API Gateway HTTP API + JWT Authorizer |
| `esm` | `local/emulator/esm.py` | Lambda SQS イベントソースマッピング |
| `dynamodb` | DynamoDB Local | DynamoDB |
| `queue` | ElasticMQ（SQS 互換） | SQS 標準キュー + DLQ |
| `bedrock-stub` | `local/emulator/bedrock_stub.py` | Amazon Bedrock Converse API |
| `github-stub` | `local/emulator/github_stub.py` | GitHub codeload / REST API |
| `frontend` | `local/emulator/frontend_server.py` | CloudFront + S3 |
| `init` | `local/emulator/init_resources.py` | Terraform（テーブル・キューの定義） |
| `test` | `local/tests/` | （ローカル専用） |

エミュレータ系のイメージは、共通ベース（Python + boto3 + `http_service.py` /
`lambda_rie.py`）の上に**そのサービスのモジュールだけ**を載せた別イメージです
（`local/emulator/Dockerfile` のマルチステージ）。1 イメージを `command` で使い分けると、
どのコンテナが何を持っているのかがイメージから読めなくなるためです。ベースは共通の親
なので、分けてもディスク上のレイヤは共有されます。

### なぜ Lambda RIE を挟むのか

`api` / `worker` は**本番と同じ Dockerfile から作った同じイメージ**を、AWS のベース
イメージに同梱されている Lambda Runtime Interface Emulator 経由で起動します。
`apigw` / `esm` はイベントを組み立てて RIE を叩くだけなので、**ハンドラ本体
（FastAPI + Mangum / Go の `worker.Handle`）は本番とまったく同じコードパスを通ります**。

ローカル用に別の `main` を書いて常駐ポーラー化すると、そこが本番と分岐した第二の
実装になります。RIE を挟む形なら、ローカル固有なのは「起動経路」だけで済みます。

## 認証の扱い

Cognito Hosted UI / PKCE / API Gateway の JWT Authorizer は docker-compose では
再現できません。**認証はバイパスします。**

重要なのは、バイパスが `apigw` エミュレータ**の中に閉じている**ことです。

- `apigw` は Bearer トークンから `sub` を取り出し、本番の Authorizer と同じ位置
  （`requestContext.authorizer.jwt.claims.sub`）へ入れて Lambda を呼びます。署名は検証しません。
- `api` コンテナは**本番の既定値のまま**動きます（`AUTH_ALLOW_UNVERIFIED_JWT` は未設定 =
  署名未検証トークンを拒否）。アプリ側にローカル用のスイッチを入れていないので、
  バイパス設定が本番ビルドへ漏れることはありません。

`sub` の決め方は次のとおりです。

1. JWT 形式（`a.b.c`）でペイロードに `sub` があれば、その値。
2. それ以外の不透明トークンは、**トークン文字列そのもの**を `sub` とみなす。

このため `Authorization: Bearer alice` と送れば `user_id=alice` として扱われ、テストが
利用者を切り替えられます。ブラウザから使う場合は `frontend` が生成する `config.js` が
`sessionStorage` へダミーのセッションを注入し、ログイン済み状態から始まります
（既定の利用者は `local-user`。`LOCAL_AUTH_SUBJECT` で変更可）。

なお画面の「ログアウト」ボタンは Cognito の URL へ飛ぶため、ローカルでは機能しません。

## Bedrock を実物へ切り替える

既定は `bedrock-stub` です（オフライン・課金ゼロ・決定的）。生成品質を実物で
確認したいときだけ、実 Bedrock（ap-northeast-1）へ向けます。**ワーカーのコードは
変わりません。**エンドポイントと資格情報を環境変数で差し替えるだけです。

```bash
# 1. 一時的な資格情報を取り出す（.env や compose ファイルへ値を書かないこと）
eval "$(aws configure export-credentials --profile <your-profile> --format env)"

# 2. Bedrock だけ実エンドポイントへ向けて起動し直す
#    生成に数十秒かかるため、可視性タイムアウト・リース・テストの待ち時間も併せて
#    引き上げる（既定の 5 秒のままだと処理中に再配信され、重複生成になります）
export LOCAL_BEDROCK_ENDPOINT=https://bedrock-runtime.ap-northeast-1.amazonaws.com
export LOCAL_AWS_ACCESS_KEY_ID="$AWS_ACCESS_KEY_ID"
export LOCAL_AWS_SECRET_ACCESS_KEY="$AWS_SECRET_ACCESS_KEY"
export LOCAL_AWS_SESSION_TOKEN="$AWS_SESSION_TOKEN"
export LOCAL_QUEUE_VISIBILITY_TIMEOUT="180 seconds"
export LOCAL_PROCESSING_LEASE_SECONDS=180
export LOCAL_JOB_TIMEOUT_SECONDS=300
export LOCAL_DLQ_TIMEOUT_SECONDS=1000

docker compose -f .devcontainer/compose.app.yaml up -d --wait

# 3. 同じ統合テストが通ることを確認する（Bedrock 分の課金が発生します）
bash scripts/integration-test.sh
```

> DLQ の検証は「可視性タイムアウト x maxReceiveCount(5)」だけ待つため、上記の設定では
> 15 分ほどかかります。生成品質だけを見たい場合は
> `PYTEST_ARGS="-k not dead_letter" bash scripts/integration-test.sh` で外してください。

DynamoDB と SQS はローカルのままです（`AWS_ENDPOINT_URL_DYNAMODB` /
`AWS_ENDPOINT_URL_SQS` が優先されるため、実アカウントのテーブルには触れません）。

同じ仕組みで GitHub も実物へ向けられます。

```bash
LOCAL_GITHUB_CODELOAD_BASE_URL=https://codeload.github.com \
LOCAL_GITHUB_API_BASE_URL=https://api.github.com \
docker compose -f .devcontainer/compose.app.yaml up -d --wait
```

## 主な環境変数

| 変数 | 既定値 | 用途 |
|---|---|---|
| `LOCAL_FRONTEND_HOST_PORT` | `8080` | 画面を publish するホスト側ポート |
| `LOCAL_API_HOST_PORT` | `8081` | API を publish するホスト側ポート |
| `LOCAL_QUEUE_HOST_PORT` | `9324` | キューを publish するホスト側ポート |
| `LOCAL_AUTH_SUBJECT` | `local-user` | 画面から使う固定ユーザーの `sub` |
| `LOCAL_CORS_ALLOW_ORIGINS` | `http://localhost:8080` | 許可オリジン（本番の `cors_allow_origins` 相当） |
| `LOCAL_BEDROCK_ENDPOINT` | `http://bedrock-stub:8080` | Bedrock のエンドポイント |
| `LOCAL_GITHUB_CODELOAD_BASE_URL` | `http://github-stub:8080` | codeload のベース URL |
| `LOCAL_GITHUB_API_BASE_URL` | `http://github-stub:8080` | GitHub REST API のベース URL |
| `LOCAL_QUEUE_VISIBILITY_TIMEOUT` | `5 seconds` | キューの可視性タイムアウト（単位付きで指定） |
| `LOCAL_PROCESSING_LEASE_SECONDS` | `5` | ワーカーの processing リース |
| `LOCAL_JOB_TIMEOUT_SECONDS` | `120` | 統合テストがジョブ完了を待つ上限 |
| `LOCAL_DLQ_TIMEOUT_SECONDS` | `150` | 統合テストが DLQ 到達を待つ上限 |
| `INTEGRATION_TEST_DOWN` | 未設定 | `1` で統合テスト後にスタックを破棄 |
| `PYTEST_ARGS` | 未設定 | pytest へ渡す追加引数（例: `-k not dead_letter`） |

これらはシェルの環境変数として渡します。compose ファイルが `.devcontainer/` 配下に
あるため、compose が既定で読む `.env` も `.devcontainer/.env` になります。リポジトリ直下の
`.env`（`GEMINI_API_KEY` 等の秘密情報）が compose へ流れ込むことはありません。

## 本番と一致しない点

「本番と同じ」を名乗る以上、**一致しない点は明示します。**

| 項目 | 本番 | ローカル | 理由 |
|---|---|---|---|
| 認証 | Cognito Hosted UI + PKCE、JWT 署名検証 | `apigw` がバイパス | Cognito にローカル代替がない |
| Bedrock | 実モデル | 既定はスタブ（切替可） | ローカル代替がなく、テストの決定性と課金ゼロを優先 |
| GitHub | 実リポジトリ | 既定はスタブ（切替可） | オフラインでの完走を優先 |
| キューの可視性タイムアウト | 1800 秒 | 5 秒 | 本番値だと DLQ 到達の検証に 2.5 時間かかる |
| `PROCESSING_LEASE_SECONDS` | 900 秒 | 5 秒 | 上記に合わせ、リースの意味を保ったまま短縮 |
| ワーカーの同時実行 | `maxConcurrency=5` | 実質 1 | RIE は 1 実行環境しか持たない |
| CloudFront | キャッシュ・OAC・署名 | 素の静的配信 | 配信層は本検証の対象外 |
| 日次集計 | Step Functions + EventBridge | 再現しない | compose に乗らない（scope.out） |

再現していない層に起因する不具合は、ローカルでは見つかりません。ここが
「ローカルで通ったから本番でも通る」と言えない境界です。

## 設計上の注意

- **bind mount を使っていません。** この devcontainer は docker-outside-of-docker 構成で、
  ホスト側デーモンから見たパスとコンテナ内のパスが一致しないためです。フロントエンドの
  静的ファイルなどはイメージへ `COPY` で焼き込みます。コードを変更したら
  `docker compose -f .devcontainer/compose.app.yaml up -d --build` で反映してください。
- **統合テストはコンテナの中で走ります**（`test` サービス）。pytest / boto3 / requests を
  devcontainer 側へ入れずに済ませ、素のホストからでも同じ手順で通るようにするためです。
