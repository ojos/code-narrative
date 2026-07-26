# Intake: frontend の変換フォーム入力をブラウザに保存して復元する

- 起票日: 2026-07-26
- 起票者ロール: intake-manager
- ステータス: **完了**（2026-07-26。PR #73 を squash merge / main `9f2eb79`。acceptance 参照）
- 起票先: [ojos/code-narrative#72](https://github.com/ojos/code-narrative/issues/72)（`completed` でクローズ）

## intake 判定

| 項目 | 値 |
|---|---|
| intake 要否 | 必要 |
| reason_code | `SMALL_FIX_REQUIRES_INTAKE` |
| 判定時の不足項目 | `acceptance`(missing) / `priority`(missing) / `constraints`(required_for_risk_control) |
| 充足状況 | Q1 の確認により必須項目を充足 |

軽微修正の免除条件のうち条件 6「ユーザーの依頼文だけから `goal` と `acceptance` が一意に読み取れ、解釈の余地がない」を満たさないため免除不成立。依頼文「ブラウザ側に保存してリロードしてもリロード前と同じ状態で復元される」からは、次が一意に定まらない。

- 保存先が `localStorage` か `sessionStorage` か（後者でも「リロードで復元」は成立する）
- ログアウト時に保存値を破棄するか保持するか（共用ブラウザでの情報残留に関わる）
- ホワイトリストから外れたモデル ID が保存されていた場合の復元挙動
- 保存の契機が入力ごとか送信成功時か

## intake 票

```yaml
goal: >
  frontend の変換フォームの 3 入力（GitHub リポジトリ URL / カスタムプロンプト /
  モデル選択）をブラウザに永続化し、ページをリロードしてもリロード前と同じ入力状態で
  復元されるようにする。同じリポジトリを繰り返し試す際の再入力をなくす。

scope.in:
  - apps/frontend/js/preferences.js を新規追加
      - Storage を注入可能な load / save / clear の 3 関数を公開する
      - 保存先は localStorage、キーは cn.form.draft（既存 auth.js の cn. 接頭辞に揃える）
      - 読み出し時に値を検証する
          - model_id: isAllowedModel() に通らなければ破棄し既定（先頭モデル）へフォールバック
          - custom_prompt: API 上限の 2000 文字で切り詰める
          - repo_url: 文字列以外は破棄する
          - JSON として壊れている場合はキーを削除し初期状態を返す
  - apps/frontend/js/app.js の配線
      - wireStaticUi の renderModelOptions 後に保存値を復元する
      - 3 入力の input / change イベントで保存する
      - ログアウト時に clear を呼ぶ
  - apps/frontend/test/preferences.test.js を新規追加
  - ドキュメント追記
      - docs/SPEC.md §5 frontend 主要機能に入力復元の仕様を追記
      - apps/frontend/README.md に保存キー・保存対象・破棄条件を追記

scope.out:
  - 変換履歴・生成結果・ジョブ ID の永続化（結果は既に履歴 API から取得できる）
  - サーバー側（DynamoDB / API）へのユーザー設定の保存
  - 認証トークンの保存方式の変更（sessionStorage のまま据え置く）
  - 複数プロファイル・保存スロットの管理 UI
  - プロンプトプリセットの追加・編集機能

constraints:
  - 保存先は localStorage とし、ログアウト時に破棄する
      共用ブラウザで次の利用者に前の利用者のリポジトリ URL が見えることを防ぐため
  - 認証トークンは対象外。sessionStorage のまま変更しない
  - localStorage が使用不可（Safari プライベートモード等で参照が例外になる場合）でも
    フォームは従来どおり動作すること。保存・復元は静かに無効化する
  - 依存パッケージを追加しない（frontend は依存ゼロの静的 SPA として維持する）
  - 既存の 3 入力の id（repo-url / custom-prompt / model-select）を変更しない

acceptance:
  - 機械検証: apps/frontend で `npm run verify`（lint → node --test → build）が終了コード 0
  - test/preferences.test.js が以下を検証している
      1. 保存 → 読み出しで 3 値が一致する
      2. ホワイトリスト外の model_id は既定モデルへフォールバックする
      3. 2000 文字超の custom_prompt は 2000 文字へ切り詰められる
      4. 壊れた JSON はキー削除のうえ初期状態を返す
      5. 空ストレージでは初期状態を返す
      6. getItem / setItem が例外を投げる Storage でも呼び出し側へ例外を伝播しない
      7. clear 後の読み出しが初期状態を返す
  - 手動確認: リポジトリ URL・カスタムプロンプト・モデルを入力してリロードすると
    3 値がすべて復元される。ログアウト後に再ログインすると 3 値が初期状態に戻る

priority: medium
```

## 確認済みの決定事項

| # | 論点 | 決定 | 理由 |
|---|---|---|---|
| Q1 | 保存先とログアウト時の扱い | `localStorage` に保存し、**ログアウト時に破棄** | タブを閉じても入力が残る利便性を取りつつ、共用ブラウザでの情報残留を避ける |
| D1 | 保存の契機 | `input` / `change` イベントごと | 送信成功時のみだと、送信前にリロードした場合に復元されず goal を満たさない |
| D2 | 保存キー | `cn.form.draft`（単一キーに JSON でまとめる） | `auth.js` の `cn.` 接頭辞慣習に揃える。単一キーなら破棄が 1 回の `removeItem` で済む |
| D3 | 復元値の検証 | 読み出し側で行う | ホワイトリストは `models.js` が正本であり、保存後にホワイトリストが変わる（実績あり: #37）ため、書き込み時の検証では不足する |

## 実施タスク順序

| # | タスク | 依存 | 並列可 | 結果 |
|---|---|---|---|---|
| T1 | `js/preferences.js` を追加（Storage 注入・検証つき load/save/clear） | — | — | 完了 |
| T2 | `js/app.js` へ復元・保存・ログアウト時破棄を配線 | T1 | T3 と並列可 | 完了 |
| T3 | `test/preferences.test.js` を追加（acceptance の 7 ケース） | T1 | T2 と並列可 | 完了（8 ケースへ増）|
| T4 | `docs/SPEC.md` §5 と `apps/frontend/README.md` を追記 | — | T1〜T3 と並列可 | 完了（SPEC は §4⑤）|
| T5 | `npm run verify` で受け入れ検証、ローカル二段ゲート通過後に PR | T2, T3, T4 | — | 完了（PR #73）|

## 着手前の事前条件

- なし。インフラ変更・外部リソース操作を伴わないため、AWS 認証や Terraform の状態に依存しない。

## 検証観点

- **回帰**: 既存 `test/auth.test.js` が `sessionStorage` を使う。`preferences.js` は `localStorage` を別キー空間（`cn.form.*`）で使うため衝突しない。`npm run verify` で確認する。
- **例外安全**: `localStorage` へのアクセス自体が例外になる環境がある。`preferences.js` 内で捕捉し、フォームの初期化を止めないこと。
- **XSS**: 復元値は `value` プロパティへ代入するのみで `innerHTML` を経由しない（`ui.js` の方針を踏襲）。

## 完了記録（2026-07-26）

### acceptance の充足

**機械検証** — `scripts/loop-gate.sh` → `GATE_PASS`

- step 1 `verify`: `VERIFY_PASS`（api 55 passed / lambda-worker・lambda-stats `go test` ok / frontend 35 tests 0 fail）
- step 2 第二意見: `[gemini-review] reviewing staged` → `LGTM`
- CI: `build-frontend` / `changes` / `verify-commit-identity` すべて pass
- Copilot レビュー: 6/6 ファイルをレビューし指摘 0 件

**手動確認** — 実 Chromium で `apps/frontend` を起動して駆動（12 チェック全 PASS）

- 3 値がリロード後に復元される。モデルは既定の Claude Sonnet 4.5 ではなく、選択した DeepSeek V3.2 が復元されることを確認
- プリセット（太宰治風）で入れた本文もリロードを跨いで復元される
- ログアウトで `cn.form.draft` が破棄され、再訪時に 3 欄すべて初期状態へ戻る

Cognito Hosted UI は本物を叩けないため `sessionStorage` にトークンを直接置いて認証済みビューを出し、API / Cognito 宛リクエストは中断した。`localStorage` の挙動そのものは実ブラウザで検証している。

### 計画からの差分

| # | 差分 | 理由 |
|---|---|---|
| 1 | テストを 7 → 8 ケースへ増やした | 「JSON だがオブジェクトでない保存値（配列等）」を追加。`normalizeDraft` が素通りしないことを固定するため |
| 2 | プリセットボタン押下時の保存を追加した | 計画に無かった経路。`value` への直接代入では `input` が発火せず、プリセットを選んでリロードすると値が失われる。手動確認でこの経路が効いていることを確認済み |
| 3 | SPEC の追記先は §5 ではなく **§4⑤** | フロントエンド仕様の実際の節番号に合わせた |

### 未了

- 本番デプロイは未実施。`deploy` ワークフローが `production` 環境の必須レビュアー承認待ちで停止している（設計どおりのゲート）

## 関連

- 判定根拠の分類: [REASON_CODES](../../.ai-playbook/intake/REASON_CODES.md)
- 票の雛形: [intake-template](../../.ai-playbook/intake/intake-template.md)
- タスク分解手順: [plan-breakdown](../../.ai-playbook/task-playbooks/plan-breakdown.md)
- 仕様: [SPEC.md](../SPEC.md) §5 Frontend
