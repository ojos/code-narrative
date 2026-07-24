# apps/frontend — 管理画面 (CloudFront + S3 静的Web)

Cognito Hosted UI（Authorization Code Grant + PKCE）でログインし、リポジトリ URL 入力・モデル選択・変換実行・履歴一覧を提供する静的 SPA。

- 配信: CloudFront + S3（OAC による直接アクセス制御）
- 公開ドメイン: `code-narrative.ojos.jp`（子アカウントへ委任したサブドメイン）

仕様は [../../docs/SPEC.md](../../docs/SPEC.md) §4 ⑤ を参照。実装は Phase 3 で行う。
