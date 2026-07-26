#!/usr/bin/env bash
set -euo pipefail
echo "[on-attach] bootstrap active"

# スクリプト自身の位置から解決する（起動時 CWD に依存しない）。scripts/ の 1 階層上がルート。
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HELPER="$HERE/load-project-env.sh"

# 対話シェルでプロジェクト .env を自動 override 読み込みするための rc 注入（冪等）。
# これにより、ターミナルの gemini CLI / スクリプト / loop-gate が .env の値を優先する。
inject_env_autoload() {
  local rc="$1"
  local marker="# >>> ojos-code-narrative project .env autoload >>>"
  # rc が無いベースイメージでも autoload を効かせるため、存在しなければ作成する
  # （touch は既存ファイルを切り詰めない）。zsh 未導入環境で作られても無害（誰も読まない）。
  [[ -f "$rc" ]] || touch "$rc"
  grep -qF "$marker" "$rc" && return 0
  {
    echo ""
    echo "$marker"
    echo "if [[ -f \"$HELPER\" ]]; then . \"$HELPER\"; fi"
    echo "# <<< ojos-code-narrative project .env autoload <<<"
  } >> "$rc"
  echo "[on-attach] injected project .env autoload into $rc"
}
inject_env_autoload "$HOME/.bashrc"
inject_env_autoload "$HOME/.zshrc"

# git identity の無害化（#47）。VS Code の copyGitConfig がリビルドのたびに
# ホストの ~/.gitconfig をコンテナへコピーし直すため、接続のたびに再適用する。
# 失敗しても on-attach 全体は落とさない。identity が未適用でも、未指定のまま
# コミットしようとすれば git 自身が止めるため、ここで打ち切る理由がない。
if ! bash "$HERE/setup-git-identity.sh"; then
  echo "[on-attach] WARN: git identity の適用に失敗しました。" >&2
  # CWD に依存しないよう絶対パスで案内する（そのままコピペして実行できる形）。
  echo "[on-attach] WARN: 手動確認: bash $HERE/setup-git-identity.sh --check" >&2
fi

# Docker レジストリ資格情報のホスト転送を打ち消す（#68）。
# VS Code は接続のたびに ~/.docker/config.json へ credsStore: dev-containers-<id> を
# 書き込む。これはホストのキーチェーンへ問い合わせるヘルパーで、git credential helper と
# 同じ構造。ホストで docker login した瞬間、コンテナ内の docker push が黙ってその
# 資格情報を使う状態になる。credsStore を落として、コンテナ内で明示的に docker login
# したときだけ通るようにする。
reset_docker_credstore() {
  local cfg="$HOME/.docker/config.json"
  [[ -f "$cfg" ]] || return 0
  python3 - "$cfg" <<'PY' || echo "[on-attach] WARN: ~/.docker/config.json の credsStore を除去できませんでした" >&2
import json, sys
path = sys.argv[1]
try:
    with open(path) as f:
        cfg = json.load(f)
except (OSError, ValueError):
    # 壊れた config を書き換えて悪化させない。
    sys.exit(1)
store = cfg.pop("credsStore", None)
if store is None:
    sys.exit(0)
with open(path, "w") as f:
    json.dump(cfg, f, indent=2)
print(f"[on-attach] removed docker credsStore: {store}")
PY
}
reset_docker_credstore

if command -v gh >/dev/null 2>&1; then
  gh auth status >/dev/null 2>&1 && echo "[on-attach] gh auth OK" || echo "[on-attach] WARN: gh auth missing"
fi
echo "[on-attach] profile list: bash scripts/github-account-switch.sh list"