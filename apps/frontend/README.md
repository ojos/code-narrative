# apps/frontend — 管理画面 (CloudFront + S3 静的Web)

Cognito Hosted UI（Authorization Code Grant + PKCE）でログインし、リポジトリ URL 入力・モデル選択・変換実行・履歴一覧を提供するフレームワーク非依存の静的 SPA（バニラ JS + ES モジュール）。

- 配信: CloudFront + S3（OAC による直接アクセス制御）
- 公開ドメイン: `code-narrative.ojos.jp`（子アカウントへ委任したサブドメイン）
- 仕様: [../../docs/SPEC.md](../../docs/SPEC.md) §4 ⑤

## ディレクトリ構成

```text
apps/frontend/
├── index.html          # 画面骨格。config.js → js/app.js の順に読み込む
├── styles.css          # スタイル（単一ファイル）
├── config.example.js   # 実行時設定の雛形（値なし。実値はコミットしない）
├── js/
│   ├── app.js          # エントリ / オーケストレーション
│   ├── config.js       # window.APP_CONFIG の検証・派生 URL 組み立て
│   ├── auth.js         # Cognito 認証（Authorization Code + PKCE）
│   ├── pkce.js         # PKCE / state 生成（Web Crypto）
│   ├── api.js          # REST API クライアント（Bearer JWT）
│   ├── models.js       # 許可モデルホワイトリスト / プロンプトプリセット
│   ├── validation.js   # 入力バリデーション（GitHub URL 等）
│   └── ui.js           # DOM 描画（ビュー層）
├── scripts/
│   ├── build.js        # dist/ を生成（依存ゼロ）
│   └── check.js        # 全 JS を node --check（lint 相当）
└── test/               # node:test による単体テスト
```

## 開発コマンド

いずれも非対話・終了コード判定可（CI/受け入れ検証で利用）。

| コマンド | 内容 |
|---|---|
| `npm run lint` | 全 JS の構文検証（`node --check`） |
| `npm test` | 単体テスト（`node --test`） |
| `npm run build` | 配信アセットを `dist/` へ生成（T5 の `aws s3 sync` 対象） |
| `npm run verify` | lint → test → build を直列実行 |

`dist/` は再生成物のためコミットしない（`.gitignore` 済み）。

## 実行時設定の注入（config.js）

設定値はハードコードせず、`window.APP_CONFIG` から読み取る。**実値は T5(CI) がデプロイ時に
`config.js` を生成して S3 へ配置する**（terraform outputs から注入）。リポジトリには雛形の
`config.example.js` のみを置く（実 `config.js` は `.gitignore` 済み）。

CI が生成すべき `config.js` の項目（対応する terraform output は feat/t3-iac）:

| APP_CONFIG キー | 値のソース |
|---|---|
| `apiEndpoint` | output `api_endpoint`（HTTP API のベース URL） |
| `region` | `ap-northeast-1`（固定） |
| `cognitoUserPoolId` | output `cognito_user_pool_id` |
| `cognitoClientId` | output `cognito_client_id` |
| `cognitoHostedUiDomain` | output `cognito_hosted_ui_domain`（ドメインプレフィックスのみ） |
| `redirectUri` | `https://code-narrative.ojos.jp/callback` |
| `logoutUri` | `https://code-narrative.ojos.jp/` |

Hosted UI / authorize / token / logout の各 URL は `cognitoHostedUiDomain` と `region` から
`js/config.js` が組み立てる（`https://<domain>.auth.<region>.amazoncognito.com`）。

ローカルで構造確認する場合は `config.example.js` を `config.js` にコピーして値を埋める。
本物の `config.js` が無い場合、`npm run build` は雛形を `dist/config.js` にフォールバック配置する。

## 認証フロー（PKCE）

1. ログイン: code_verifier / code_challenge(S256) / state を生成・保存し、Hosted UI の
   `/oauth2/authorize`（`response_type=code`）へリダイレクト。
2. コールバック: `/callback?code&state` を受領 → state 照合 → `/oauth2/token` で
   code_verifier を用いてトークン交換 → sessionStorage に保持。
3. API 呼び出し: アクセストークンを `Authorization: Bearer` で付与。失効間近は
   refresh_token で更新。
4. ログアウト: トークン破棄後に Hosted UI `/logout` へリダイレクト。

Implicit フローは使用しない。コールバック/ログアウト URL は T3 の Cognito 設定
（`https://code-narrative.ojos.jp/callback` / `https://code-narrative.ojos.jp/`）と一致。

## SPA ルーティングの前提

`/callback` は SPA のパスであり、CloudFront/S3 側で `index.html` を返す設定（403/404 を
`/index.html` にフォールバック等）が必要。アプリはパスに依らずクエリの `code` を検出して処理する。
