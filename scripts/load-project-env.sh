#!/usr/bin/env bash
# load-project-env.sh — プロジェクト固有の .env を「ホスト由来の環境変数より優先」で読み込む。
#
# 目的: devcontainer の remoteEnv がホスト OS の GEMINI_API_KEY をコンテナへ注入する構造
#       （.devcontainer/devcontainer.json）は維持したまま、本プロジェクトのみ .env の値を
#       上書き優先する。
#
# 使い方: 実行ではなく source して使う。
#   . scripts/load-project-env.sh
#
# 設計:
#   - 対象 .env はスクリプト自身の位置から解決する（CWD 非依存・パス非ハードコード）。
#     scripts/ の 1 階層上をルートとみなす。別ディレクトリ名でクローンしても追随し、
#     別リポジトリへ cd 済みのシェルから source しても誤検出しない（rc 側は絶対パスを注入）。
#     OJOS_PROJECT_ENV_FILE で明示的に差し替え可能。
#   - .env は source せず安全にパースする（KEY=VALUE のみ export、任意コードは実行しない）。
#     これにより、壊れた .env が対話シェルの初期化ごと落とす事故を防ぐ。
#   - CRLF・=前後や値前後の空白など、実務的な .env の揺れを吸収する。
#
# 冪等: 複数回 source しても安全。.env が無ければ何もしない。

__ojos_load_project_env() {
  local project_root env_file line key val src
  # ソース中ファイルのパスを bash / zsh 双方で解決する。zsh には BASH_SOURCE が無いため
  # ${BASH_SOURCE[0]} は空になり CWD 依存へ化ける。実行シェルを判定して回避する。
  if [ -n "${BASH_VERSION:-}" ]; then
    src="${BASH_SOURCE[0]}"
  elif [ -n "${ZSH_VERSION:-}" ]; then
    # zsh: 現在ソース中ファイルの絶対/相対パス。
    src="${(%):-%x}"
  else
    src="$0"
  fi
  # スクリプト位置から解決（scripts/ の 1 階層上がルート）。CWD にもパスにも依存しない。
  project_root="$(cd "$(dirname "$src")/.." && pwd)"
  env_file="${OJOS_PROJECT_ENV_FILE:-$project_root/.env}"
  [[ -f "$env_file" ]] || return 0

  while IFS= read -r line || [[ -n "$line" ]]; do
    # CRLF 対策: Windows ホストでクローンされた .env の CR を除去。
    line="${line//$'\r'/}"
    # 行の前後の空白を除去し、空行・コメント行はスキップ。
    line="${line#"${line%%[![:space:]]*}"}"
    line="${line%"${line##*[![:space:]]}"}"
    [[ -z "$line" || "$line" == \#* ]] && continue
    # 先頭の `export` 記法を許容。区切りがスペース以外（タブ等）でも剥がせるよう、
    # まず `export` 文字列だけを落としてから先頭空白をトリムする。
    if [[ "$line" == export[[:space:]]* ]]; then
      line="${line#export}"
      line="${line#"${line%%[![:space:]]*}"}"
    fi
    # KEY=VALUE 形式でなければスキップ。
    [[ "$line" == *=* ]] || continue
    key="${line%%=*}"
    val="${line#*=}"
    # キー前後の空白を除去し、正当な識別子だけを対象にする（KEY = VALUE を許容）。
    key="${key//[[:space:]]/}"
    [[ "$key" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]] || continue
    # 値の前後の空白を除去（KEY= VALUE / KEY =VALUE 等）。クォート内の空白は後段で保持。
    val="${val#"${val%%[![:space:]]*}"}"
    val="${val%"${val##*[![:space:]]}"}"
    # 値を囲む対のクォートがあれば外す（dotenv 慣習）。
    if [[ ${#val} -ge 2 && "$val" == \"*\" ]]; then
      val="${val:1:${#val}-2}"
    elif [[ ${#val} -ge 2 && "$val" == \'*\' ]]; then
      val="${val:1:${#val}-2}"
    fi
    # 後勝ちで既存の環境変数（remoteEnv 由来のホスト値）を上書きする。
    export "$key=$val"
  done < "$env_file"
}

__ojos_load_project_env
