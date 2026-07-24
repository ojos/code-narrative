#!/usr/bin/env bash
set -euo pipefail
echo "[check] bootstrap checks"
for cmd in bash jq gh docker rg; do
  command -v "$cmd" >/dev/null 2>&1 && echo "[check] $cmd OK" || echo "[check] $cmd missing"
done
command -v node >/dev/null 2>&1 && echo "[check] node OK" || echo "[check] node missing"
command -v python >/dev/null 2>&1 && echo "[check] python OK" || echo "[check] python missing"
command -v go >/dev/null 2>&1 && echo "[check] go OK" || echo "[check] go missing"
command -v aws >/dev/null 2>&1 && echo "[check] aws OK" || echo "[check] aws missing"
command -v gcloud >/dev/null 2>&1 && echo "[check] gcloud OK" || echo "[check] gcloud missing"
command -v terraform >/dev/null 2>&1 && echo "[check] terraform OK" || echo "[check] terraform missing"
command -v claude >/dev/null 2>&1 && echo "[check] claude OK" || echo "[check] claude missing"
command -v gemini >/dev/null 2>&1 && echo "[check] gemini OK" || echo "[check] gemini missing"