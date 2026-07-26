#!/usr/bin/env bash
# fix-mount-owner.sh — 永続 named volume のマウントポイント所有権を現ユーザーへ戻す。
#
# 空の named volume を初回マウントすると、マウントポイントが Docker デーモン（root）に
# よって root:root 所有で作られ、remoteUser が書き込めない。各 CLI のログインやキャッシュ
# 書き込みがそこで失敗するため、postCreate の最初に所有権を戻す。
#
# 対象は「認証状態・設定を持ち、リビルドをまたいで保持したいディレクトリ」（.devcontainer/compose.yaml）。
#
# 設計:
#   - 冪等。既に現ユーザー所有なら再帰 chown を避ける（不要な再帰 I/O の回避）。
#   - マウントされていないディレクトリは触らない。
#   - **失敗しても exit 0 を返す。** postCreateCommand は後続で AI CLI 導入を実行するため、
#     ここで止めると復旧手段（CLI）ごと失われる。問題は WARN で可視化する。
set -uo pipefail

TARGETS=(
  "/home/vscode/.claude"
  "/home/vscode/.gemini"
  "/home/vscode/.aws"
  "/home/vscode/.config/gcloud"
  "/home/vscode/.config/gh"
)

fix_owner() {
  local dir="$1"
  local want owner
  # マウントされていない設定ディレクトリは触らない。
  [[ -d "$dir" ]] || {
    echo "[fix-mount-owner] $dir does not exist, skipping"
    return 0
  }
  want="$(id -un)"
  owner="$(stat -c %U "$dir" 2>/dev/null || stat -f %Su "$dir" 2>/dev/null || echo '')"
  if [[ "$owner" == "$want" ]]; then
    echo "[fix-mount-owner] $dir already owned by $want, skipping chown"
    return 0
  fi
  # sudo が無い環境（ベースイメージ非依存）でも異常終了させない。
  if ! command -v sudo >/dev/null 2>&1; then
    echo "[fix-mount-owner] WARN: sudo not available; cannot fix owner of $dir" >&2
    return 0
  fi
  echo "[fix-mount-owner] fixing owner of $dir -> $(id -un):$(id -gn)"
  # chown 失敗（busy 等）でも後続を止めない。
  if ! sudo chown -R "$(id -un):$(id -gn)" "$dir"; then
    echo "[fix-mount-owner] WARN: failed to fix owner of $dir" >&2
  fi
}

for dir in "${TARGETS[@]}"; do
  fix_owner "$dir"
done
echo "[fix-mount-owner] done"
exit 0
