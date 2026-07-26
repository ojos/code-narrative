#!/usr/bin/env bash
# setup-git-identity.sh — identity 未指定のコミットを「黙って通す」経路を塞ぐ
#
# 背景 (#45 / #47):
#   リポジトリ初期の 8 コミットが個人所属の identity (aizu@bascule.co.jp) で
#   main に入り、GitHub の Contributors に別アカウントが現れた。原因は
#   「local 設定を持たないリポジトリが、黙って global にフォールバックする」こと。
#   リポジトリを新規作成した時点では local 設定が存在しないため、そこが穴になる。
#
#   コンテナの ~/.gitconfig は VS Code の dev.containers.copyGitConfig が
#   ホストの設定をコピーして生成する。リビルドのたびに再生成されるため、
#   一度きりの適用では戻る。接続のたびに再適用する前提で書く。
#
#   なお .git/config (local) は workspace がホストの bind mount であるため
#   リビルドでは失われない。ここで local を扱うのは、消えた場合の復旧と、
#   このリポジトリで useConfigOnly の失敗に遭わせないための保険。
#
# 適用する内容:
#   1. global の user.name / user.email を削除する
#   2. global に user.useConfigOnly=true を立てる
#      → local 未設定のリポジトリでは commit が exit 128 で止まる。
#         黙って別名義になるより、止まって気づくほうがよい。
#   3. 当リポジトリの local へ ojos identity を適用する
#   4. global の credential.helper を空 → gh に固定する (#68)
#      → VS Code はホストの資格情報へ転送するヘルパーを /etc/gitconfig と
#         ~/.gitconfig の両方へ注入する。実測では、打ち消していないディレクトリで
#         `git credential fill` が別アカウント (bascule-aizu) の PAT を警告なく返した。
#         空文字を 1 つ置くと git はそれまでのヘルパー一覧を破棄するため、system
#         (/etc/gitconfig) 側の注入も無効化できる。そのうえで gh を唯一の供給元にする。
#         gh 未ログイン時は https 操作が失敗するが、黙って別アカウントで通るより
#         止まって気づくほうがよい。identity (3) と同じ考え方。
#
# github-account-switch.sh を呼ばないのは、あれが gh api user / gh auth login を
# 伴うため。接続のたびにネットワークを叩くのは重く、オフラインやトークン未設定で
# 失敗する。ここでは git identity だけを env から適用する。認証の切替えは
# 引き続き github-account-switch.sh の役割。
#
# 使い方:
#   bash scripts/setup-git-identity.sh            # 適用
#   bash scripts/setup-git-identity.sh --check    # 検証
#
#   --check は「適用をもう一度実行して状態が変化しないこと」も併せて検証する
#   （冪等性と、credential セクションを壊していないことの確認を兼ねる）。
#
# 終了コード:
#   0 = IDENTITY_SETUP_OK / 1 = IDENTITY_SETUP_FAIL
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$(dirname "$HERE")"

# GIT_AUTHOR_*_OJOS はプロジェクト .env / devcontainer の remoteEnv 由来。
# shellcheck source=scripts/load-project-env.sh
. "$HERE/load-project-env.sh"

EXPECTED_NAME="${GIT_AUTHOR_NAME_OJOS:-}"
EXPECTED_EMAIL="${GIT_AUTHOR_EMAIL_OJOS:-}"

# git が資格情報を要求したときの唯一の供給元。gh のログイン状態に紐づくため、
# 未ログインなら供給されず、git は黙って別経路へ落ちずに失敗する。
GH_CREDENTIAL_HELPER='!gh auth git-credential'

log() { echo "[git-identity] $*"; }
err() { echo "[git-identity] $*" >&2; }

# 一時ファイルはスクリプトスコープで持ち、EXIT で片付ける。
# RETURN トラップにすると main の復帰時にも発火し、local が解放済みの状態で
# 参照して set -u に殺される。
SNAPSHOT=""
TMP_SNAPSHOT=""
TMP_REPO=""
cleanup() {
  [[ -n "$SNAPSHOT" ]] && rm -f "$SNAPSHOT"
  [[ -n "$TMP_SNAPSHOT" ]] && rm -f "$TMP_SNAPSHOT"
  [[ -n "$TMP_REPO" ]] && rm -rf "$TMP_REPO"
  return 0
}
trap cleanup EXIT

# git が実際に書き込む global 設定ファイルの実体を git 自身に問い合わせる。
# ~/.gitconfig と XDG 配下のどちらが使われるかは環境で変わるため、決め打ちしない。
resolve_global_config() {
  local origin
  origin="$(git config --global --show-origin --get user.useConfigOnly 2>/dev/null | head -1 || true)"
  if [[ "$origin" == file:* ]]; then
    origin="${origin#file:}"
    printf '%s' "${origin%%$'\t'*}"
    return 0
  fi
  printf '%s' "${GIT_CONFIG_GLOBAL:-$HOME/.gitconfig}"
}

# 失敗は必ず return 1 で返す。
# この関数は `if ! apply` の条件文脈から呼ばれることがあり、その中では set -e が
# 無効化される。書き込み失敗を素通りさせると最後の log の終了コード 0 が返り、
# 「適用できていないのに成功」と報告してしまう。
apply() {
  # --unset-all は該当キーが無いと exit 5 を返す。未設定は正常系なので握りつぶす。
  git config --global --unset-all user.name || true
  git config --global --unset-all user.email || true

  if ! git config --global user.useConfigOnly true; then
    err "ERROR: global 設定に user.useConfigOnly を書き込めません"
    return 1
  fi

  # credential.helper をリセットして gh に固定する (#68)。
  # --unset-all で VS Code が global へ注入したヘルパーを除去し、空文字で system
  # (/etc/gitconfig) 側の注入も破棄したうえで、gh を唯一の供給元として積む。
  # 順序が重要で、空文字が先に来なければ system 側が残る。
  git config --global --unset-all credential.helper || true
  if ! git config --global --add credential.helper '' ||
    ! git config --global --add credential.helper "$GH_CREDENTIAL_HELPER"; then
    err "ERROR: global 設定に credential.helper を書き込めません"
    return 1
  fi

  if [[ -n "$EXPECTED_NAME" && -n "$EXPECTED_EMAIL" ]]; then
    if ! git config --local user.name "$EXPECTED_NAME" ||
      ! git config --local user.email "$EXPECTED_EMAIL"; then
      err "ERROR: local 設定に identity を書き込めません"
      return 1
    fi
    log "local identity: $EXPECTED_NAME <$EXPECTED_EMAIL>"
  else
    # ここで落とさない。global の無害化は済んでおり、identity 未設定のまま
    # コミットしようとすれば git 自身が exit 128 で止める。
    err "WARN: GIT_AUTHOR_NAME_OJOS / GIT_AUTHOR_EMAIL_OJOS が未設定のため local identity を適用しません。"
    err "WARN: このリポジトリでコミットする前に次を実行してください:"
    err "WARN:   bash $HERE/github-account-switch.sh use ojos --git-scope local"
  fi

  log "global identity を無効化し user.useConfigOnly=true を設定しました"
}

# 期待どおりに identity が解決できない状態を作って、git が止まることを確かめる。
# GIT_AUTHOR_* / EMAIL が環境にあると git はそれを使うため、判定から除外する。
git_ident_without_env() {
  env -u GIT_AUTHOR_NAME -u GIT_AUTHOR_EMAIL \
      -u GIT_COMMITTER_NAME -u GIT_COMMITTER_EMAIL \
      -u EMAIL \
      git "$@"
}

check() {
  local failures=0
  local global_config ident

  global_config="$(resolve_global_config)"

  # 状態の検査を先に行う。適用を先に走らせると「未適用」を検出できなくなるため、
  # 冪等性の検査（apply を伴う）は最後に置く。
  SNAPSHOT="$(mktemp)"
  TMP_SNAPSHOT="$(mktemp)"
  cp "$global_config" "$SNAPSHOT" 2>/dev/null || : >"$SNAPSHOT"

  # 1) global に identity が残っていないこと。
  if [[ -z "$(git config --global --get user.name || true)" ]]; then
    log "OK  global user.name は未設定"
  else
    err "NG  global user.name が残っている: $(git config --global --get user.name)"
    failures=$((failures + 1))
  fi
  if [[ -z "$(git config --global --get user.email || true)" ]]; then
    log "OK  global user.email は未設定"
  else
    err "NG  global user.email が残っている: $(git config --global --get user.email)"
    failures=$((failures + 1))
  fi

  # 2) 未指定コミットを失敗させる設定が効いていること。
  if [[ "$(git config --global --get user.useConfigOnly || true)" == "true" ]]; then
    log "OK  user.useConfigOnly=true"
  else
    err "NG  user.useConfigOnly が true でない"
    failures=$((failures + 1))
  fi

  # 3) 当リポジトリの local identity。
  if [[ -n "$EXPECTED_EMAIL" ]]; then
    if [[ "$(git config --local --get user.email || true)" == "$EXPECTED_EMAIL" ]]; then
      log "OK  local user.email = $EXPECTED_EMAIL"
    else
      err "NG  local user.email が $EXPECTED_EMAIL でない: $(git config --local --get user.email || echo '<unset>')"
      failures=$((failures + 1))
    fi
  else
    log "SKIP GIT_AUTHOR_EMAIL_OJOS 未設定のため local identity の検査を省略"
  fi

  # 4) 当リポジトリでは identity が解決できること。
  if ident="$(git_ident_without_env var GIT_AUTHOR_IDENT 2>/dev/null)"; then
    log "OK  当リポジトリの author: ${ident% * *}"
  else
    err "NG  当リポジトリで author identity を解決できない"
    failures=$((failures + 1))
  fi

  # 5) local 設定を持たないリポジトリでは identity 解決が失敗すること。
  #    これが本題。黙って global へ落ちないことを確かめる。
  TMP_REPO="$(mktemp -d)"
  git init -q "$TMP_REPO"
  if (cd "$TMP_REPO" && git_ident_without_env var GIT_AUTHOR_IDENT >/dev/null 2>&1); then
    err "NG  local 未設定のリポジトリで author identity が解決できてしまう"
    err "NG  → 未設定のままコミットが通る。#45 の混入経路が塞がっていない。"
    failures=$((failures + 1))
  else
    log "OK  local 未設定のリポジトリでは author identity 解決が失敗する"
  fi
  rm -rf "$TMP_REPO"
  TMP_REPO=""

  # 6) credential.helper が「空 → gh」の順で global に固定されていること (#68)。
  # 空文字の helper は空行として出力されるため、期待値は「空行 + gh」の 2 行。
  local helpers expected_helpers
  helpers="$(git config --global --get-all credential.helper 2>/dev/null || true)"
  expected_helpers=$'\n'"$GH_CREDENTIAL_HELPER"
  if [[ "$helpers" == "$expected_helpers" ]]; then
    log "OK  global credential.helper = 空 → gh"
  else
    err "NG  global credential.helper が「空 → gh」でない:"
    printf '%s\n' "$helpers" | sed 's/^/[git-identity] NG    /' >&2
    failures=$((failures + 1))
  fi

  # 7) local 設定を持たないリポジトリで、ホストの資格情報が供給されないこと。
  #    VS Code は接続のたびにホストへ転送するヘルパーを注入する。5) の identity と
  #    同じ構図で、こちらは「誰の権限で通信するか」を見る。
  TMP_REPO="$(mktemp -d)"
  git init -q "$TMP_REPO"
  local cred_out got_password gh_token
  cred_out="$(printf 'protocol=https\nhost=github.com\n\n' |
    timeout 30 git -C "$TMP_REPO" credential fill 2>/dev/null || true)"
  got_password="$(printf '%s\n' "$cred_out" | sed -n 's/^password=//p')"
  # gh 自身が持つトークン。GH_TOKEN が環境にあればそれを返すため、helper の出力と
  # 同じ供給元になる。トークンそのものは表示せず、一致だけを見る。
  gh_token="$(gh auth token 2>/dev/null || true)"
  if [[ -n "$gh_token" ]]; then
    if [[ "$got_password" == "$gh_token" ]]; then
      log "OK  local 未設定のリポジトリでも資格情報の供給元は gh のみ"
    else
      err "NG  gh 以外の供給元から資格情報が返っている（ホストへ転送されている疑い）"
      failures=$((failures + 1))
    fi
  else
    if [[ -z "$got_password" ]]; then
      log "OK  gh 未ログイン時は資格情報が供給されない（ホストへ落ちない）"
    else
      err "NG  gh 未ログインなのに資格情報が返った（ホストの資格情報が使われている）"
      failures=$((failures + 1))
    fi
  fi
  rm -rf "$TMP_REPO"
  TMP_REPO=""

  # 8) 冪等性 + credential セクションの保全。
  #    適用をもう一度走らせ、global 設定ファイルが 1 バイトも変わらないことを見る。
  #    credential.helper は VS Code が注入するため、消していないことを併せて確認する。
  #
  #    この検査は apply を伴う。未適用の状態で走らせると「失敗を報告しながら
  #    裏で直してしまう」ことになり、次回の --check が通って問題が見えなくなる。
  #    先行する検査が落ちている場合は、意味を持たないので実行しない。
  if [[ "$failures" -gt 0 ]]; then
    log "SKIP 冪等性検査（先行する検査が失敗しているため。まず適用してください）"
  else
    # apply の失敗を握りつぶすと、何も書き換わらないので cmp が一致し、
    # 「再適用できないのに冪等 OK」という誤った判定になる。失敗は失敗として扱う。
    if ! apply >/dev/null 2>&1; then
      err "NG  再適用に失敗した（apply が非ゼロ終了）"
      failures=$((failures + 1))
    else
      cp "$global_config" "$TMP_SNAPSHOT" 2>/dev/null || : >"$TMP_SNAPSHOT"
      if cmp -s "$SNAPSHOT" "$TMP_SNAPSHOT"; then
        log "OK  冪等: 再適用で $global_config は変化しない（credential セクションを含む）"
      else
        err "NG  冪等性なし: 再適用で $global_config が変化した"
        diff -u "$SNAPSHOT" "$TMP_SNAPSHOT" >&2 || true
        failures=$((failures + 1))
      fi
    fi
  fi

  if [[ "$failures" -gt 0 ]]; then
    err "$failures 件の検査に失敗しました。"
    echo "IDENTITY_SETUP_FAIL"
    return 1
  fi

  echo "IDENTITY_SETUP_OK"
  return 0
}

main() {
  case "${1-}" in
    --check) check ;;
    "") apply ;;
    -h | --help)
      # 先頭コメントブロックをそのままヘルプとして出す（行番号を決め打ちしない）。
      awk 'NR==1{next} /^#/{sub(/^# ?/,""); print; next} {exit}' "${BASH_SOURCE[0]}"
      ;;
    *)
      err "error: unknown option: $1"
      exit 1
      ;;
  esac
}

main "$@"
