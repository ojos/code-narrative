#!/usr/bin/env bash
# gemini-review.sh — 別ベンダーのモデルによる第二意見（クロスモデル二段ゲートの ②段目）
#
# 規範: .ai-playbook/review-workflow.md
# 目的: 実装したモデル自身の自己レビューは盲点を共有するため、別ベンダーのモデルで
#       独立にクロスチェックする。push 前のローカル事前ゲートで使う。
#
# 使い方:
#   bash scripts/gemini-review.sh              # ステージ済み差分をレビュー
#   bash scripts/gemini-review.sh --range main..HEAD
#
# 終了コード:
#   0 = LGTM（重大な指摘なし。push 可）
#   1 = 重大な指摘あり、または実行不能
set -euo pipefail

RANGE=""
MODEL="${GEMINI_REVIEW_MODEL:-}"

usage() {
  cat <<'EOF'
usage: bash scripts/gemini-review.sh [options]

options:
  --range <git-range>   レビュー対象の差分範囲（既定: ステージ済み差分）
  --model <name>        使用モデル（既定: gemini CLI の既定。GEMINI_REVIEW_MODEL でも指定可）
  -h, --help            ヘルプ
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --range) RANGE="$2"; shift 2 ;;
    --model) MODEL="$2"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "error: unknown option: $1" >&2; usage; exit 1 ;;
  esac
done

command -v gemini >/dev/null 2>&1 || {
  echo "error: gemini CLI not found. run scripts/install-ai-tools.sh" >&2
  exit 1
}
[[ -n "${GEMINI_API_KEY:-}" ]] || {
  echo "error: GEMINI_API_KEY is not set" >&2
  exit 1
}

if [[ -n "$RANGE" ]]; then
  diff_text="$(git diff "$RANGE")"
  scope="$RANGE"
else
  diff_text="$(git diff --cached)"
  scope="staged"
fi

if [[ -z "${diff_text//[[:space:]]/}" ]]; then
  echo "[gemini-review] no diff to review ($scope)"
  exit 0
fi

# ゲート対象は review-workflow.md の限定に合わせる。
read -r -d '' PROMPT <<'EOF' || true

上記は git の差分です。コードレビューを行ってください。

指摘対象は次の 4 点に限定します。それ以外は報告しないでください。
- 致命バグ
- 脆弱性
- 型エラー
- エッジケースの見落とし

報告しないもの:
- 好みのリファクタリング
- 命名や可読性の軽微な提案
- 差分の範囲外にある既存コードの問題

出力形式:
- 上記 4 点に該当する指摘が 1 件もなければ、`LGTM` とだけ出力してください。
- 指摘がある場合は、各指摘について「該当ファイルと行」「何が問題か」「なぜ問題か（再現条件や影響）」を簡潔に記述してください。
EOF

echo "[gemini-review] reviewing $scope"
# 差分を stdin で渡すだけで、モデルにツール実行は不要。信頼済みフォルダの確認は
# 対話を要求するため、非対話実行では明示的に読み取り専用として扱う。
args=(--skip-trust -p "$PROMPT")
[[ -n "$MODEL" ]] && args=(-m "$MODEL" "${args[@]}")

output="$(printf '%s' "$diff_text" | gemini "${args[@]}" 2>&1)" || {
  echo "error: gemini review failed" >&2
  printf '%s\n' "$output" >&2
  exit 1
}

printf '%s\n' "$output"

# 通過判定はモデルの出力ゆれに耐える必要がある。LGTM とだけ返すよう指示していても、
# **LGTM** / `LGTM` / LGTM. のように装飾されることがある。装飾・空白・句点を除いてから
# 行単位で厳密一致させる（文中の LGTM は通過させない）。
if printf '%s\n' "$output" \
  | sed 's/[`*_#]//g; s/[[:space:]]//g; s/[.。]$//' \
  | grep -qix 'LGTM'; then
  echo "[gemini-review] LGTM"
  exit 0
fi

echo "[gemini-review] findings reported. fix them in a single iteration before push." >&2
exit 1
