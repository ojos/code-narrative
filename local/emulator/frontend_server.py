"""フロントエンド静的配信のローカルサーバ（CloudFront + S3 の代替）。

`apps/frontend` をそのまま配信し、`/config.js` だけを実行時に生成する。
本番では CI がデプロイ時に `config.js` を生成して S3 へ置くため（`config.js` は
`.gitignore` 済み）、生成物をここで差し替えても本番のファイルには一切触れない。

生成する `config.js` は次の 2 つを行う。

1. `window.APP_CONFIG` の設定（API エンドポイントはブラウザから見える公開 URL）。
2. **ローカル専用の認証バイパス**: Cognito が無いため、`sessionStorage` へ
   ダミーのトークンを注入して SPA をログイン済み状態にする。トークン文字列は
   そのまま `sub` として `apigw` に解釈される。

本モジュールはローカル検証専用であり、本番には含まれない。
"""

from __future__ import annotations

import json
import os
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

from http_service import configure_logging, env_int

logger = configure_logging("frontend")

LISTEN_PORT = env_int("LOCAL_FRONTEND_PORT", 8080)
STATIC_ROOT = os.environ.get("LOCAL_FRONTEND_ROOT", "/srv/frontend")
# ブラウザ（ホスト側）から見た API の公開 URL。compose の ports 設定と揃える。
API_PUBLIC_URL = os.environ.get("LOCAL_API_PUBLIC_URL", "http://localhost:8081")
# ローカルの固定ログインユーザー（DynamoDB の user_id になる）。
LOCAL_SUBJECT = os.environ.get("LOCAL_AUTH_SUBJECT", "local-user")
# 画面から開いたときの自分自身の公開 URL（リダイレクト先の体裁を整えるためだけに使う）。
FRONTEND_PUBLIC_URL = os.environ.get("LOCAL_FRONTEND_PUBLIC_URL", "http://localhost:8080")

# AuthClient が sessionStorage に使うキー（apps/frontend/js/auth.js の STORAGE_KEYS）。
_TOKEN_STORAGE_KEY = "cn.auth.tokens"


def render_config_js() -> bytes:
    """`window.APP_CONFIG` とローカル用ダミーセッションを含む config.js を生成する。

    Returns:
        UTF-8 エンコード済みの JavaScript。
    """

    app_config = {
        "apiEndpoint": API_PUBLIC_URL,
        "region": os.environ.get("AWS_REGION", "ap-northeast-1"),
        # Cognito は再現しないが、config.js の必須キー検証を通すため値を埋める。
        "cognitoUserPoolId": "ap-northeast-1_local0000",
        "cognitoClientId": "local-client-id",
        "cognitoHostedUiDomain": "code-narrative-local",
        "redirectUri": f"{FRONTEND_PUBLIC_URL}/callback",
        "logoutUri": f"{FRONTEND_PUBLIC_URL}/",
    }

    # 失効判定を確実に回避するため、十分に先の固定エポック秒を入れる（2286-11-20）。
    tokens = {"access_token": LOCAL_SUBJECT, "expires_at": 9999999999}

    script = f"""// このファイルはローカル環境が実行時に生成しています（リポジトリには存在しません）。
// 本番では CI が terraform outputs から同じ構造の config.js を生成します。
window.APP_CONFIG = {json.dumps(app_config, ensure_ascii=False, indent=2)};

// --- ローカル専用の認証バイパス ---
// Cognito Hosted UI / PKCE は docker-compose では再現できないため、ダミーの
// セッションを注入してログイン済み状態から始める。access_token はそのまま
// sub として apigw エミュレータに解釈される（署名検証は行われない）。
(function seedLocalSession() {{
  try {{
    if (window.sessionStorage.getItem({json.dumps(_TOKEN_STORAGE_KEY)}) === null) {{
      window.sessionStorage.setItem(
        {json.dumps(_TOKEN_STORAGE_KEY)},
        {json.dumps(json.dumps(tokens))},
      );
    }}
  }} catch (error) {{
    console.error("ローカルセッションの注入に失敗しました。", error);
  }}
}})();
"""
    return script.encode("utf-8")


class FrontendHandler(SimpleHTTPRequestHandler):
    """静的ファイルを配信し、`/config.js` だけを動的生成するハンドラ。"""

    protocol_version = "HTTP/1.1"

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler の規約
        """GET リクエストを処理する。"""

        if self.path.split("?", 1)[0] == "/config.js":
            self._send_config_js()
            return
        super().do_GET()

    def _send_config_js(self) -> None:
        """生成した config.js を返す。"""

        body = render_config_js()
        self.send_response(200)
        self.send_header("Content-Type", "application/javascript; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        """アクセスログを標準のロガーへ流す。

        Args:
            format: 書式文字列。
            args: 書式引数。
        """

        logger.debug("%s - %s", self.address_string(), format % args)


def main() -> None:
    """静的配信サーバを起動する。"""

    handler = partial(FrontendHandler, directory=STATIC_ROOT)
    server = ThreadingHTTPServer(("0.0.0.0", LISTEN_PORT), handler)
    logger.info(
        "listening on port %d (root=%s, api=%s, sub=%s)",
        LISTEN_PORT,
        STATIC_ROOT,
        API_PUBLIC_URL,
        LOCAL_SUBJECT,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:  # pragma: no cover - コンテナ停止時の正常経路
        logger.info("shutting down")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
