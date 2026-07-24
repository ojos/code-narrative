#!/usr/bin/env bash
# loop-gate.sh — ローカル事前ゲート（ループコーディングの収束点）
#
# push / PR 作成の前に、機械判定の受け入れ検証（verify.sh）と、任意の第二意見
# レビューを直列で通す単一入口。verify が通り、第二意見があればそれも通ったときだけ
# 通過する。
#
# このスクリプトは単体で動作する。第二意見レビューは存在すれば直列化し、
# 無ければ優雅にスキップする（外部パッケージの導入を前提にしない）。
#
# 第二意見レビュー:
#   既定で scripts/gemini-review.sh があれば実行する。
#   LOOP_GATE_REVIEW_CMD で任意のコマンドへ差し替え可能。空文字でスキップする。
#
# 終了コード:
#   0 = GATE_PASS（全段通過。push 可）
#   1 = GATE_FAIL（いずれかの段が未通過、または実行不能）
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# verify・第二意見（git diff 等）はプロジェクトルート基準で実行する。
# scripts/ の 1 階層上がルート。任意の作業ディレクトリから起動しても不変にする。
cd "$(dirname "$HERE")"

echo "[loop-gate] step 1: verify (acceptance)"
if ! bash "$HERE/verify.sh"; then
  echo "[loop-gate] verify not passed" >&2
  echo "GATE_FAIL"
  exit 1
fi

echo "[loop-gate] step 2: second opinion"
if [[ "${LOOP_GATE_REVIEW_CMD-__UNSET__}" == "__UNSET__" ]]; then
  if [[ -f "$HERE/gemini-review.sh" ]]; then
    if ! bash "$HERE/gemini-review.sh"; then
      echo "[loop-gate] second opinion reported findings" >&2
      echo "GATE_FAIL"
      exit 1
    fi
  else
    echo "[loop-gate] SKIP (no reviewer present)"
  fi
elif [[ -n "$LOOP_GATE_REVIEW_CMD" ]]; then
  if ! bash -c "$LOOP_GATE_REVIEW_CMD"; then
    echo "[loop-gate] second opinion reported findings" >&2
    echo "GATE_FAIL"
    exit 1
  fi
else
  echo "[loop-gate] SKIP (disabled by LOOP_GATE_REVIEW_CMD='')"
fi

echo "GATE_PASS"
exit 0