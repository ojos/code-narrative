#!/usr/bin/env bash
set -euo pipefail
echo "[on-attach] bootstrap active"
if command -v gh >/dev/null 2>&1; then
  gh auth status >/dev/null 2>&1 && echo "[on-attach] gh auth OK" || echo "[on-attach] WARN: gh auth missing"
fi
echo "[on-attach] profile list: bash scripts/github-account-switch.sh list"