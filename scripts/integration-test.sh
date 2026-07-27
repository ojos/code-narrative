#!/usr/bin/env bash
# integration-test.sh — ローカル環境を起動し、統合テストを非対話で実行する。
#
# 実 AWS リソースへは接続しない。Bedrock と GitHub はスタブへ向くため、AWS 資格情報が
# 未設定でも、外部ネットワークへ到達できなくても完走する（issue #74）。
#
# 使い方:
#   bash scripts/integration-test.sh
#
# 環境変数:
#   INTEGRATION_TEST_DOWN=1  終了後にスタックを破棄する（既定は起動したまま残す）。
#   PYTEST_ARGS="-k xxx"     pytest へ渡す追加引数。
#
# 終了コード: 0 = 合格 / 非0 = 不合格
set -euo pipefail

# ルート基準で compose を解決する。scripts/ の 1 階層上がリポジトリルート。
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(dirname "$HERE")"
cd "$ROOT"

if ! command -v docker >/dev/null 2>&1; then
  echo "[integration] docker が見つかりません。Docker をインストールしてください。" >&2
  exit 1
fi

if ! docker compose version >/dev/null 2>&1; then
  echo "[integration] docker compose (v2) が使えません。" >&2
  exit 1
fi

if ! docker info >/dev/null 2>&1; then
  echo "[integration] docker デーモンへ接続できません。" >&2
  exit 1
fi

cleanup() {
  if [[ "${INTEGRATION_TEST_DOWN:-0}" == "1" ]]; then
    echo "[integration] スタックを破棄します"
    docker compose down -v --remove-orphans || true
  fi
}
trap cleanup EXIT

echo "[integration] スタックを起動します (docker compose up -d --wait --build)"
if ! docker compose up -d --wait --build; then
  echo "[integration] 起動に失敗しました。直近のログを出力します。" >&2
  docker compose ps || true
  docker compose logs --tail 100 || true
  exit 1
fi

# test サービスは profile 配下のため、上の `up --build` の対象にならない。
# 明示的にビルドしないと、テストコードを変更しても古いイメージのまま実行される。
echo "[integration] テストイメージをビルドします"
if ! docker compose build test; then
  echo "[integration] テストイメージのビルドに失敗しました。" >&2
  exit 1
fi

echo "[integration] 統合テストを実行します"

# `docker compose run` にアタッチしたまま実行すると、環境によっては途中で標準出力の
# ストリームが切れ、失敗したテストの詳細が読めなくなる（終了コードは正しい）。
# デタッチして実行し、終了を待ってからログをまとめて取り出す。
#
# --no-deps: 依存は上の `up --wait` で起動済み。ここで再起動させない。
# shellcheck disable=SC2086 # PYTEST_ARGS は複数引数として展開させる
test_container="$(docker compose run -d --no-deps test \
  python -m pytest -v --color=no ${PYTEST_ARGS:-} 2>/dev/null)"

if [[ -z "$test_container" ]]; then
  echo "[integration] テストコンテナを起動できませんでした。" >&2
  exit 1
fi

remove_test_container() {
  docker rm -f "$test_container" >/dev/null 2>&1 || true
}
trap 'remove_test_container; cleanup' EXIT

test_exit="$(docker wait "$test_container")"
docker logs "$test_container" 2>&1

if [[ "$test_exit" != "0" ]]; then
  echo "[integration] 統合テストが失敗しました (exit ${test_exit})。直近のログを出力します。" >&2
  docker compose logs --tail 200 api worker esm apigw || true
  exit 1
fi

echo "[integration] OK"
