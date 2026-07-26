# 実行環境向け入口ファイル

このファイルは、AI エージェントの実行環境が最初に読む入口です。
実行環境ごとに 1 ファイル用意します（例: `CLAUDE.md`、`.github/copilot-instructions.md`）。

## 指示の適用順序

次の順序でルールを適用します（下位から上位へ優先）。

1. `.ai-playbook/shared-ai-rules.md`（全体共通ルール）
2. `.github/project-ai-rules.md`（プロジェクト共通ルール）
3. このファイル（実行環境固有の最小差分）

下位ルールと上位ルールが矛盾する場合は、上位を優先します。

## この入口ファイルの責務

- このファイルは最小構成に保ち、実行環境固有の差分のみを扱います。
- このファイルでロール責務を再定義しません。ロール責務は `.ai-playbook/role-contracts/` を参照します。
- このファイルでタスク手順を再定義しません。タスク手順は `.ai-playbook/task-playbooks/` を参照します。
- このファイルでレビュー運用を再定義しません。レビュー運用は `.ai-playbook/review-workflow.md` を参照します。

## Claude Code 固有の差分

### intake の起点

実装・修正・issue 起票を求められた場合は、`.claude/skills/intake/` を起点に intake の要否を判定します。規範の正本は `.ai-playbook/intake/` であり、スキル側では再定義しません。

このスキルは Claude Code 固有の配線です。他の実行環境（`.github/copilot-instructions.md` 等）は、同じ規範を各環境の機構で参照します。

### スキル定義のファイル名

`.claude/skills/*/SKILL.md` は Claude Code の機構が要求する固定ファイル名です。`.ai-playbook/shared-ai-rules.md` 8 章の「スキル定義は `lower-kebab-case.md`」の例外として扱います。

## 導入時の調整

- 規範の配置先が `.ai-playbook` 以外の場合は、上記のパスを実際の配置先へ置き換えます。
- この節は、調整が済んだら削除してかまいません。
