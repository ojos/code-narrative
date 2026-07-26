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

# 永続 volume の所有権修正は scripts/fix-mount-owner.sh が担う（#66）。対象が AI ツール以外
# （aws / gcloud / gh）へ広がったため、postCreateCommand の前段へ分離した。
install_if_missing claude "@anthropic-ai/claude-code"
install_if_missing gemini "@google/gemini-cli"
echo "[install-ai-tools] done"