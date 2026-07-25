# プロジェクト共通 AI ルール

このファイルはプロジェクト共通ルールの正本です。
全体共通ルールを、このプロジェクトの事情に合わせて具体化します。

## 参照先

- 全体共通ルール: `.ai-playbook/shared-ai-rules.md`
- ロール責務: `.ai-playbook/role-contracts/`
- タスク手順: `.ai-playbook/task-playbooks/`
- レビュー運用: `.ai-playbook/review-workflow.md`
- intake 規律・判定根拠: `.ai-playbook/intake/`

実行環境の入口ファイル（`CLAUDE.md` 等）はこのファイルを参照し、最小差分のみを記述します。

## このプロジェクト固有の値

（プロジェクト固有の制約・検証手順を記述します）

## 機密の具体化

共通規範「機密の取り扱い」を、このプロジェクトで具体化します。

- 機密の読み取り元: （例: `.env` / シークレット管理サービス）
- 追跡除外の対象: （例: `.env`）
- 共有する雛形: （例: 値のない `.env.example`）

## 生成物の具体化

- コミットしない生成物: （例: ビルド成果物、メディアファイル）
- 再生成手順: （コマンドを記載）

## 作業状況の記録先

共通規範「作業状況の記録」を、このプロジェクトで具体化します。
単一ファイルへの集中更新は並列実行と衝突するため、追記のみの形式や作業単位ごとの分割を検討します。

- 未完了の作業: （記録先を記載）
- 完了した作業の履歴: （記録先を記載）

## 外部サービスの状態管理

共通規範「外部サービスの状態管理」を、このプロジェクトで具体化します。

- 対象の外部状態: （例: クラウドリソース、公開リポジトリ、リリース）
- 宣言・適用の手段: （例: Terraform、専用スクリプト）
- 手動操作の扱い: 状態確認・調査に留め、恒久的な変更は宣言側を通す

## レビューの起動方法

共通規範「レビューワークフロー」のクロスモデル二段ゲートを、このプロジェクトで具体化します。

1. 主レビュー: 実装したモデル自身で、`scripts/verify.sh`（受け入れ検証）が緑になった後にステージ済み差分を自己レビューし、その場で修正する。
2. 第二意見: 別ベンダー（Google Gemini）のモデルで独立にクロスチェックする。`bash scripts/gemini-review.sh`（ステージ済み差分）または `bash scripts/gemini-review.sh --range <git-range>`（例: `main..HEAD`）で実行する。`LGTM` のみ出力（終了コード 0）で通過、指摘ありは終了コード 1。
   - 前提: `gemini` CLI（`scripts/install-ai-tools.sh --with-gemini`）と環境変数 `GEMINI_API_KEY`。
3. 単一入口: `bash scripts/loop-gate.sh` が「受け入れ検証（`verify.sh`）→ 第二意見（`gemini-review.sh`）」を直列化する。push / PR 作成の前にこれを通す。第二意見コマンドは `LOOP_GATE_REVIEW_CMD` で差し替え・無効化できる。

- 両段とも対象は致命バグ・脆弱性・型エラー・エッジケースの見落としに限ります。
- 修正は 1 イテレーションで完結させます。

### リモート最終ゲート（Copilot）

- push / PR 作成後の GitHub 上の最終ゲートは GitHub Copilot のコードレビューを用います。
- PR 作成時に**一度だけ**自動要求します。機構は `.github/workflows/copilot-review.yml`（`pull_request: [opened]` で `copilot-pull-request-reviewer[bot]` をレビュアー要求）。
- 前提: リポジトリ所有者の Copilot サブスクリプションで Copilot code review が有効なこと。無効な場合はワークフローが失敗するため、有効化するか本ゲートを無効化します。既定トークンで要求できない場合は Secrets `COPILOT_REVIEW_TOKEN`（PAT）で切り替えます。
- 最終ゲートは共通規範どおり 1 回のみ要求します（`.ai-playbook/review-workflow.md`）。
