#!/usr/bin/env bash
# acceptance.sh — このプロジェクトの受け入れ条件（プロジェクトが所有・編集する）
#
# verify.sh がこのスクリプトを実行し、終了コードで合否を判定する。
# この monorepo の各アプリを、存在するものだけ、それぞれの慣習的なテストで検証する。
# 受け入れ条件が検証可能であるほど、ループコーディングの反復が収束しやすくなる。
#
#   - apps/api           : uv（pyproject.toml）前提で uv run pytest
#   - apps/lambda-worker : Go（go.mod）で go test ./...
#   - apps/frontend      : 未実装。テストが定義されたら追加する。
#
# 未実装・不在のアプリはスキップし、失敗させない。存在するアプリのテストが
# 1 つでも落ちれば非0 で終了する。
#
# 終了コード: 0 = 合格 / 非0 = 不合格
set -euo pipefail

# ルート基準で各アプリを解決する。scripts/ の 1 階層上がリポジトリルート。
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(dirname "$HERE")"
cd "$ROOT"

# uv は既定の PATH に無いことがある（スタンドアロンインストール先）。
# set -u 下でも HOME 未定義環境でクラッシュしないようフォールバックする。
export PATH="${HOME:-}/.local/bin:$PATH"

ran_any=0

echo "[acceptance] monorepo acceptance checks"

# --- apps/api (Python / uv) ---
if [[ -f apps/api/pyproject.toml ]]; then
  command -v uv >/dev/null 2>&1 || {
    echo "[acceptance] uv not found. install: https://docs.astral.sh/uv/ (curl -LsSf https://astral.sh/uv/install.sh | sh)" >&2
    exit 1
  }
  echo "[acceptance] (apps/api) uv sync --frozen && uv run --frozen pytest"
  ( cd apps/api && uv sync --frozen && uv run --frozen pytest )
  ran_any=1
else
  echo "[acceptance] (apps/api) skip: pyproject.toml not found"
fi

# --- apps/lambda-worker (Go) ---
if [[ -f apps/lambda-worker/go.mod ]]; then
  command -v go >/dev/null 2>&1 || {
    echo "[acceptance] go not found. install Go toolchain to run apps/lambda-worker tests." >&2
    exit 1
  }
  echo "[acceptance] (apps/lambda-worker) go test ./..."
  ( cd apps/lambda-worker && go test ./... )
  ran_any=1
else
  echo "[acceptance] (apps/lambda-worker) skip: go.mod not found"
fi

# --- apps/frontend (未実装) ---
if [[ -f apps/frontend/package.json ]]; then
  command -v npm >/dev/null 2>&1 || {
    echo "[acceptance] npm not found. install Node.js to run apps/frontend tests." >&2
    exit 1
  }
  echo "[acceptance] (apps/frontend) npm test"
  ( cd apps/frontend && npm test )
  ran_any=1
else
  echo "[acceptance] (apps/frontend) skip: package.json not found (未実装)"
fi

if [[ "$ran_any" -eq 0 ]]; then
  echo "[acceptance] no app was verified. 受け入れ対象が 1 つも見つかりません。" >&2
  exit 1
fi

echo "[acceptance] OK"
