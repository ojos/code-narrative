#!/usr/bin/env bash
# 選択された AI CLI ツールを導入する（--with-claude / --with-gemini / --with-copilot）。
set -euo pipefail

install_if_missing() {
  local cmd="$1"
  local pkg="$2"
  if command -v "$cmd" >/dev/null 2>&1; then
    echo "[install-ai-tools] $cmd already installed, skipping"
    return 0
  fi
  echo "[install-ai-tools] installing $pkg ..."
  npm install -g "$pkg"
  echo "[install-ai-tools] $cmd installed: $(command -v "$cmd")"
}

# AI ツールの永続 named volume を空の状態で初回マウントすると、マウントポイントが
# Docker デーモン（root）により root:root 所有で作られ、remoteUser が書き込めず
# CLI のログインが失敗する。設定ディレクトリの所有権を現ユーザーへ戻して復旧する。
fix_owner() {
  local dir="$1"
  local want owner
  # マウントされていない設定ディレクトリは触らない。
  [[ -d "$dir" ]] || return 0
  want="$(id -un)"
  # 既に現ユーザー所有なら再帰 chown を避ける（冪等・不要な再帰 I/O 回避）。
  owner="$(stat -c %U "$dir" 2>/dev/null || stat -f %Su "$dir" 2>/dev/null || echo '')"
  if [[ "$owner" == "$want" ]]; then
    echo "[install-ai-tools] $dir already owned by $want, skipping chown"
    return 0
  fi
  # sudo が無い環境（ベースイメージ非依存）でも set -euo pipefail 下で異常終了させない。
  if ! command -v sudo >/dev/null 2>&1; then
    echo "[install-ai-tools] WARN: sudo not available; cannot fix owner of $dir" >&2
    return 0
  fi
  echo "[install-ai-tools] fixing owner of $dir -> $(id -un):$(id -gn)"
  # chown 失敗（busy 等）でも set -euo pipefail 下で postCreate 全体を止めない。
  # sudo 不在ブランチと挙動を揃え、CLI 導入まで到達させたうえで WARN で可視化する。
  if ! sudo chown -R "$(id -un):$(id -gn)" "$dir"; then
    echo "[install-ai-tools] WARN: failed to fix owner of $dir" >&2
  fi
}

fix_owner "/home/vscode/.claude"
fix_owner "/home/vscode/.gemini"
install_if_missing claude "@anthropic-ai/claude-code"
install_if_missing gemini "@google/gemini-cli"
echo "[install-ai-tools] done"