#!/usr/bin/env bash
# acceptance.sh — このプロジェクトの受け入れ条件（プロジェクトが所有・編集する）
#
# verify.sh がこのスクリプトを実行し、終了コードで合否を判定する。
# 生成時に、選択言語の慣習的なテストコマンドを既定として配置している。
# プロジェクトの実態（テスト・ビルド・lint・E2E など）に合わせて自由に編集すること。
# 受け入れ条件が検証可能であるほど、ループコーディングの反復が収束しやすくなる。
#
# 終了コード: 0 = 合格 / 非0 = 不合格
set -euo pipefail

echo "[acceptance] project acceptance checks"
echo "[acceptance] (node) npm test"
npm test
echo "[acceptance] (python) python -m pytest"
python -m pytest
echo "[acceptance] (go) go test ./..."
go test ./...