#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
usage:
  bash scripts/github-account-switch.sh list
  bash scripts/github-account-switch.sh status
  bash scripts/github-account-switch.sh use <profile> [--git-scope local|global]

profiles:
  GITHUB_TOKEN_<PROFILE_UPPER> を設定した profile を自動検出
  任意で以下も profile ごとに設定可:
    GITHUB_OWNER_<PROFILE_UPPER>
    GIT_AUTHOR_NAME_<PROFILE_UPPER>
    GIT_AUTHOR_EMAIL_<PROFILE_UPPER>
EOF
}

profile_to_upper() {
  printf '%s' "$1" | tr '[:lower:]' '[:upper:]'
}

cmd_list() {
  local found=0
  while IFS='=' read -r key _; do
    if [[ "$key" =~ ^GITHUB_TOKEN_(.+)$ ]]; then
      local suffix="${BASH_REMATCH[1]}"
      local profile
      profile="$(printf '%s' "$suffix" | tr '[:upper:]' '[:lower:]')"
      echo "  $profile  (env: GITHUB_TOKEN_${suffix})"
      found=1
    fi
  done < <(env | sort)
  if [[ "$found" -eq 0 ]]; then
    echo "  (none — set GITHUB_TOKEN_<PROFILE> to register a profile)"
  fi
}

cmd_status() {
  echo "[github-account] gh auth status"
  gh auth status -h github.com || true
  echo
  echo "[github-account] git identity"
  echo "  scope=local  name=$(git config --local user.name 2>/dev/null || echo '<unset>')"
  echo "  scope=local  email=$(git config --local user.email 2>/dev/null || echo '<unset>')"
  echo "  scope=global name=$(git config --global user.name 2>/dev/null || echo '<unset>')"
  echo "  scope=global email=$(git config --global user.email 2>/dev/null || echo '<unset>')"
  echo "  github.owner(local)=$(git config --local github.owner 2>/dev/null || echo '<unset>')"
  echo "  github.owner(global)=$(git config --global github.owner 2>/dev/null || echo '<unset>')"
  echo
  echo "[github-account] registered profiles"
  cmd_list
}

# git push の認証を、いま選択した gh のアカウントへ向ける。
#
# gh auth login --with-token は非対話のため git を設定しない。これを補わないと、
# gh と git identity だけが切り替わり、push の認証は既存の credential.helper
# （エディタが仕込むものなど）が返す別アカウントのまま残る。切替えたつもりで
# 別人として push しようとして 403 になる。
#
# git はヘルパーを定義順に試し、最初に応答したものを採用する。上位スコープに
# ヘルパーがあると必ずそちらが勝つため、空文字を先に入れて一覧をリセットする。
setup_git_credentials() {
  local git_scope="$1"
  command -v gh >/dev/null 2>&1 || return 0
  git config --"$git_scope" --unset-all credential.helper 2>/dev/null || true
  git config --"$git_scope" --add credential.helper ''
  git config --"$git_scope" --add credential.helper '!gh auth git-credential'
}

cmd_use() {
  local profile="$1"
  shift

  [[ "$profile" =~ ^[a-zA-Z0-9_]+$ ]] || {
    echo "error: invalid profile" >&2
    exit 1
  }

  local git_scope="local"
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --git-scope)
        git_scope="$2"
        shift 2
        ;;
      *)
        echo "error: unknown option: $1" >&2
        exit 1
        ;;
    esac
  done

  local upper token_env name_env email_env owner_env
  upper="$(profile_to_upper "$profile")"
  token_env="GITHUB_TOKEN_${upper}"
  name_env="GIT_AUTHOR_NAME_${upper}"
  email_env="GIT_AUTHOR_EMAIL_${upper}"
  owner_env="GITHUB_OWNER_${upper}"

  local token="${!token_env:-}"
  [[ -n "$token" ]] || {
    echo "error: $token_env is not set" >&2
    exit 1
  }

  local login
  login="$(GH_TOKEN="$token" gh api user --jq .login)"
  printf '%s' "$token" | gh auth login --hostname github.com --with-token >/dev/null
  if gh auth switch --help >/dev/null 2>&1; then
    gh auth switch --hostname github.com --user "$login" >/dev/null
  fi

  local owner="${!owner_env:-$login}"
  local git_name="${!name_env:-}"
  local git_email="${!email_env:-}"

  if [[ -n "$git_name" ]]; then git config --"$git_scope" user.name "$git_name"; fi
  if [[ -n "$git_email" ]]; then git config --"$git_scope" user.email "$git_email"; fi
  git config --"$git_scope" github.owner "$owner"
  git config --"$git_scope" github.account "$login"

  setup_git_credentials "$git_scope"

  echo "[github-account] active profile: $profile"
  echo "[github-account] active login:   $login"
  echo "[github-account] owner:          $owner"
  echo "[github-account] git scope:      $git_scope"
  echo "[github-account] git user.name:  $(git config --"$git_scope" user.name 2>/dev/null || echo '<unchanged>')"
  echo "[github-account] git user.email: $(git config --"$git_scope" user.email 2>/dev/null || echo '<unchanged>')"
  echo "[github-account] git push auth:  gh ($login)"
}

main() {
  [[ $# -ge 1 ]] || {
    usage
    exit 1
  }

  case "$1" in
    list) cmd_list ;;
    status) cmd_status ;;
    use)
      shift
      [[ $# -ge 1 ]] || {
        echo "error: missing profile" >&2
        exit 1
      }
      cmd_use "$@"
      ;;
    -h|--help|help) usage ;;
    *)
      echo "error: unknown subcommand: $1" >&2
      usage
      exit 1
      ;;
  esac
}

main "$@"