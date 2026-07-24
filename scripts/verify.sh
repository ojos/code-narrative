#!/usr/bin/env bash
# verify.sh — ループコーディングの接地信号（受け入れ条件の機械ゲート）
#
# プロジェクトが宣言した受け入れ条件（acceptance）を非対話で実行し、
# 一意な通過信号を返す。AI エージェントの反復（実装 → 検証 → 修正 → …）が
# 「緑」を判定するための、迂回できない決定的な信号を供給する。
#
# このスクリプトは単体で動作し、外部パッケージの導入を前提にしない。
#
# 使い方:
#   bash scripts/verify.sh
#
# 受け入れ条件の定義:
#   既定で scripts/acceptance.sh を実行する。VERIFY_ACCEPTANCE で差し替え可能。
#
# 終了コード:
#   0 = VERIFY_PASS（受け入れ条件を満たす）
#   1 = VERIFY_FAIL（未達、または受け入れ条件が未定義）
set -euo pipefail

# 受け入れ検証とテストコマンド（package.json / go.mod / Cargo.toml 等の検出）は
# プロジェクトルート基準で実行する。scripts/ は生成先プロジェクト直下にあるため、
# スクリプト位置の 1 階層上がルート。任意の作業ディレクトリから起動しても不変にする。
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$(dirname "$HERE")"

ACCEPTANCE="${VERIFY_ACCEPTANCE:-scripts/acceptance.sh}"

if [[ ! -f "$ACCEPTANCE" ]]; then
  echo "[verify] acceptance not found: $ACCEPTANCE" >&2
  echo "[verify] 受け入れ条件が未定義です。実行可能な検証を用意してください。" >&2
  echo "VERIFY_FAIL"
  exit 1
fi

echo "[verify] running acceptance: $ACCEPTANCE"
if bash "$ACCEPTANCE"; then
  echo "VERIFY_PASS"
  exit 0
fi

echo "[verify] acceptance not satisfied" >&2
echo "VERIFY_FAIL"
exit 1