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
#   - 存在しないディレクトリは触らない（volume 未マウント時や、CLI 未使用でまだ作られていない場合）。
#   - sudo は非対話（-n）で実行する。パスワードを要求する環境で postCreate が入力待ちのまま
#     ハングするのを防ぐ。要求された場合は WARN してスキップする。
#   - **失敗しても exit 0 を返す。** postCreateCommand は後続で AI CLI 導入を実行するため、
#     ここで止めると復旧手段（CLI）ごと失われる。問題は WARN で可視化する。
set -uo pipefail

# 親を先に置く。ネストしたマウントポイント（.config/*）の親がイメージに存在しない場合、
# Docker が親ディレクトリごと root:root で作るため、親が root のままだと vscode は
# ~/.config 直下へ新しい設定を作れなくなる。現在のベースイメージ
# （mcr.microsoft.com/devcontainers/base:ubuntu）は .config を vscode 所有で同梱しており
# 実際には起きないが、イメージ側の事情に依存させないため防御的に対象へ含める。
# 既に vscode 所有なら所有者チェックで no-op になる。
TARGETS=(
  "/home/vscode/.config"
  "/home/vscode/.claude"
  "/home/vscode/.gemini"
  "/home/vscode/.aws"
  "/home/vscode/.config/gcloud"
  "/home/vscode/.config/gh"
)

fix_owner() {
  local dir="$1"
  local want owner
  # 存在しないディレクトリは触らない（volume 未マウント、または CLI 未使用で未作成）。
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
  # パスワードを要求する sudo 設定では非対話実行が失敗する。postCreate は対話端末を持たないため、
  # -n を付けずに実行すると入力待ちでハングする。先に判定して WARN で抜ける。
  if ! sudo -n true 2>/dev/null; then
    echo "[fix-mount-owner] WARN: sudo requires a password; skipping owner fix for $dir" >&2
    return 0
  fi
  echo "[fix-mount-owner] fixing owner of $dir -> $(id -un):$(id -gn)"
  # chown 失敗（busy 等）でも後続を止めない。
  if ! sudo -n chown -R "$(id -un):$(id -gn)" "$dir"; then
    echo "[fix-mount-owner] WARN: failed to fix owner of $dir" >&2
  fi
}

for dir in "${TARGETS[@]}"; do
  fix_owner "$dir"
done
echo "[fix-mount-owner] done"
exit 0
