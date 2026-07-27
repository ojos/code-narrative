"""GitHub（codeload / REST API）のローカルスタブ。

ワーカーは対象リポジトリの tarball とコミット履歴を GitHub から取得する。
統合テストを「ネットワーク到達不能でも成功する」状態に保つため、既定では
``GITHUB_CODELOAD_BASE_URL`` / ``GITHUB_API_BASE_URL`` をこのスタブへ向ける。

再現するのは次の 2 経路のみ。

- ``GET /{owner}/{repo}/tar.gz/HEAD`` — codeload 相当。単一の先頭ディレクトリ
  ``{repo}-HEAD/`` 配下にファイルを持つ tar.gz を、その場で生成して返す。
- ``GET /repos/{owner}/{repo}/commits?per_page=N`` — REST API 相当。

リポジトリ名が ``missing`` で始まる場合は 404 を返し、「存在しない/非公開」
（恒久エラー → status=failed 確定）の経路を検証できるようにする。

本モジュールはローカル検証専用であり、本番には含まれない。
"""

from __future__ import annotations

import io
import json
import re
import tarfile
import time
import urllib.parse

from http_service import JsonRequestHandler, configure_logging, env_int, serve_forever

logger = configure_logging("github-stub")

LISTEN_PORT = env_int("LOCAL_GITHUB_STUB_PORT", 8080)

_TARBALL_PATH = re.compile(r"^/(?P<owner>[^/]+)/(?P<repo>[^/]+)/tar\.gz/HEAD$")
_COMMITS_PATH = re.compile(r"^/repos/(?P<owner>[^/]+)/(?P<repo>[^/]+)/commits$")

# 404 を返すリポジトリ名の接頭辞（恒久エラー経路の検証用）。
_MISSING_REPO_PREFIX = "missing"

# tarball に詰めるファイル。extract.SelectMaterial が README と主要ソースを
# 拾えるよう、README と拡張子付きソースを含める。
_REPO_FILES: dict[str, str] = {
    "README.md": (
        "# stub-repo\n\n"
        "ローカル統合テスト用のスタブリポジトリです。\n"
        "GitHub へ接続せずにワーカーの抽出・生成経路を検証します。\n"
    ),
    "main.go": (
        "package main\n\n"
        'import "fmt"\n\n'
        "func main() {\n"
        '\tfmt.Println("stub repository")\n'
        "}\n"
    ),
    "internal/service/service.go": (
        "package service\n\n"
        "// Run はスタブの処理を実行する。\n"
        "func Run() string {\n"
        '\treturn "ok"\n'
        "}\n"
    ),
    "scripts/build.sh": "#!/usr/bin/env bash\nset -euo pipefail\ngo build ./...\n",
}

# コミット履歴のスタブ。日時は固定し、応答を決定的に保つ。
_COMMITS: list[dict[str, str]] = [
    {
        "message": "feat: スタブリポジトリの初期実装",
        "name": "Local Stub",
        "date": "2026-01-01T00:00:00Z",
    },
    {
        "message": "docs: README を追加",
        "name": "Local Stub",
        "date": "2026-01-02T00:00:00Z",
    },
    {
        "message": "refactor: service パッケージへ処理を分離",
        "name": "Local Stub",
        "date": "2026-01-03T00:00:00Z",
    },
]


def build_tarball(repo: str) -> bytes:
    """codeload と同じ構造（単一の先頭ディレクトリ配下）の tar.gz を生成する。

    Args:
        repo: リポジトリ名。先頭ディレクトリ名 ``{repo}-HEAD`` に用いる。

    Returns:
        gzip 圧縮された tar のバイト列。
    """

    buffer = io.BytesIO()
    top_dir = f"{repo}-HEAD"

    # mtime を固定して、同じ入力から同じバイト列が得られるようにする。
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        directory = tarfile.TarInfo(name=top_dir)
        directory.type = tarfile.DIRTYPE
        directory.mode = 0o755
        directory.mtime = 0
        archive.addfile(directory)

        for path, content in _REPO_FILES.items():
            payload = content.encode("utf-8")
            info = tarfile.TarInfo(name=f"{top_dir}/{path}")
            info.size = len(payload)
            info.mode = 0o644
            info.mtime = 0
            archive.addfile(info, io.BytesIO(payload))

    return buffer.getvalue()


def build_commits(limit: int) -> list[dict[str, object]]:
    """REST API ``/repos/{owner}/{repo}/commits`` の応答を組み立てる。

    Args:
        limit: 返す最大件数（``per_page``）。

    Returns:
        GitHub REST API 形の JSON 配列。
    """

    return [
        {
            "sha": f"{index:040x}",
            "commit": {
                "message": commit["message"],
                "author": {"name": commit["name"], "date": commit["date"]},
            },
        }
        for index, commit in enumerate(_COMMITS[: max(0, limit)])
    ]


class GitHubStubHandler(JsonRequestHandler):
    """codeload / REST API の 2 経路を受け付けるスタブハンドラ。"""

    logger = logger

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler の規約
        """GET リクエストを処理する。"""

        parsed = urllib.parse.urlsplit(self.path)
        path = urllib.parse.unquote(parsed.path)

        tarball_match = _TARBALL_PATH.match(path)
        if tarball_match is not None:
            self._serve_tarball(tarball_match.group("repo"))
            return

        commits_match = _COMMITS_PATH.match(path)
        if commits_match is not None:
            self._serve_commits(commits_match.group("repo"), parsed.query)
            return

        self.send_json(404, {"message": "Not Found"})

    def _serve_tarball(self, repo: str) -> None:
        """tarball を生成して返す。

        Args:
            repo: リポジトリ名。
        """

        if repo.startswith(_MISSING_REPO_PREFIX):
            self.logger.info("tarball: repo=%s を 404 として応答します", repo)
            self.send_json(404, {"message": "Not Found"})
            return

        payload = build_tarball(repo)
        self.logger.info("tarball: repo=%s bytes=%d", repo, len(payload))
        self.send_bytes(
            200,
            payload,
            "application/x-gzip",
            {
                "Content-Disposition": f'attachment; filename={repo}-HEAD.tar.gz',
                "Last-Modified": time.strftime(
                    "%a, %d %b %Y %H:%M:%S GMT", time.gmtime(0)
                ),
            },
        )

    def _serve_commits(self, repo: str, query: str) -> None:
        """コミット履歴を返す。

        Args:
            repo: リポジトリ名。
            query: クエリ文字列（``per_page`` を読む）。
        """

        if repo.startswith(_MISSING_REPO_PREFIX):
            self.send_json(404, {"message": "Not Found"})
            return

        parameters = urllib.parse.parse_qs(query)
        try:
            limit = int(parameters.get("per_page", ["30"])[0])
        except ValueError:
            limit = 30

        commits = build_commits(limit)
        self.logger.info("commits: repo=%s count=%d", repo, len(commits))
        self.send_bytes(
            200,
            json.dumps(commits, ensure_ascii=False).encode("utf-8"),
            "application/json; charset=utf-8",
        )


if __name__ == "__main__":
    serve_forever(GitHubStubHandler, LISTEN_PORT, logger)
