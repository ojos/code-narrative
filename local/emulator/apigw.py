"""API Gateway (HTTP API) のローカルエミュレータ。

`terraform/modules/api/apigateway.tf` の構成を写し取り、次を再現する。

- 明示ルート（``POST /api/v1/narratives`` 等）のみを受け付け、未定義パスは 404。
- ルートごとの JWT Authorizer 適用（``GET /health`` のみ認証不要）。
- 検証済み claims を ``requestContext.authorizer.jwt.claims`` へ格納した
  payload format 2.0 のイベント生成。
- ``cors_configuration`` 相当の CORS ヘッダ付与と、無一致 OPTIONS への自動 204 応答。

**認証はローカル専用のバイパス**である。Cognito の署名検証は行わず、Bearer トークン
から ``sub`` を取り出す（JWT 形式ならペイロードの ``sub``、それ以外はトークン文字列
そのもの）。バイパスはこのエミュレータ側に閉じており、API コンテナは本番と同じ既定値
（``AUTH_ALLOW_UNVERIFIED_JWT`` 未設定 = 署名未検証トークンを拒否）のまま動作する。

本モジュールはローカル検証専用であり、本番の API Gateway には含まれない。
"""

from __future__ import annotations

import base64
import binascii
import json
import os
import re
import time
import urllib.parse
import uuid
from typing import Any

from http_service import JsonRequestHandler, configure_logging, env_int, serve_forever
from lambda_rie import LambdaFunctionError, LambdaInvocationError, LambdaRieClient

logger = configure_logging("apigw")

# --- 設定（環境変数） ---

LISTEN_PORT = env_int("LOCAL_APIGW_PORT", 8080)
LAMBDA_ENDPOINT = os.environ.get("LOCAL_API_LAMBDA_ENDPOINT", "http://api:8080")
# 本番 API Lambda のタイムアウトに合わせた上限（terraform: modules/api の timeout）。
LAMBDA_TIMEOUT_SECONDS = env_int("LOCAL_API_LAMBDA_TIMEOUT", 30)
# terraform の cors_allow_origins 相当。カンマ区切り。
CORS_ALLOW_ORIGINS = [
    origin.strip()
    for origin in os.environ.get("LOCAL_CORS_ALLOW_ORIGINS", "*").split(",")
    if origin.strip()
]

# terraform の cors_configuration と同じ値。
CORS_ALLOW_HEADERS = "authorization,content-type"
CORS_ALLOW_METHODS = "GET,POST,OPTIONS"
CORS_MAX_AGE = "3600"


class Route:
    """API Gateway の 1 ルート定義。

    Attributes:
        method: HTTP メソッド。
        template: ``/api/v1/narratives/{job_id}`` 形式のパステンプレート。
        require_jwt: JWT Authorizer を適用するか。
        pattern: テンプレートから生成した照合用正規表現。
    """

    def __init__(self, method: str, template: str, *, require_jwt: bool) -> None:
        """ルートを初期化する。

        Args:
            method: HTTP メソッド。
            template: パステンプレート。
            require_jwt: JWT Authorizer を適用するか。
        """

        self.method = method
        self.template = template
        self.require_jwt = require_jwt
        self.pattern = re.compile(self._to_regex(template))

    @property
    def route_key(self) -> str:
        """``"POST /api/v1/narratives"`` 形式のルートキーを返す。

        Returns:
            ルートキー文字列。
        """

        return f"{self.method} {self.template}"

    def match(self, method: str, path: str) -> dict[str, str] | None:
        """メソッドとパスがこのルートに一致するか判定する。

        Args:
            method: リクエストの HTTP メソッド。
            path: リクエストパス（クエリを除く）。

        Returns:
            一致した場合はパスパラメータの dict、不一致なら ``None``。
        """

        if method != self.method:
            return None
        matched = self.pattern.fullmatch(path)
        if matched is None:
            return None
        return {k: urllib.parse.unquote(v) for k, v in matched.groupdict().items()}

    @staticmethod
    def _to_regex(template: str) -> str:
        """パステンプレートを名前付きキャプチャ付き正規表現へ変換する。

        Args:
            template: ``/a/{id}`` 形式のテンプレート。

        Returns:
            正規表現文字列。
        """

        parts = []
        for segment in template.split("/"):
            if segment.startswith("{") and segment.endswith("}"):
                parts.append(f"(?P<{segment[1:-1]}>[^/]+)")
            else:
                parts.append(re.escape(segment))
        return "/".join(parts)


# terraform の local.jwt_routes と health ルートを 1:1 で写す。
ROUTES: tuple[Route, ...] = (
    Route("POST", "/api/v1/narratives", require_jwt=True),
    Route("GET", "/api/v1/narratives", require_jwt=True),
    Route("GET", "/api/v1/narratives/{job_id}", require_jwt=True),
    Route("GET", "/health", require_jwt=False),
)

lambda_client = LambdaRieClient(LAMBDA_ENDPOINT, LAMBDA_TIMEOUT_SECONDS)


def resolve_subject(authorization: str | None) -> str | None:
    """Authorization ヘッダから ``sub`` を解決する（ローカル専用バイパス）。

    署名は検証しない。Cognito の代替として、次の順で ``sub`` を決める。

    1. JWT 形式（``a.b.c``）でペイロードに ``sub`` があれば、その値。
    2. それ以外の不透明トークンは、トークン文字列そのものを ``sub`` とみなす。
       これによりテストが ``Authorization: Bearer alice`` で利用者を切り替えられる。

    Args:
        authorization: ``Authorization`` ヘッダの値（未設定なら ``None``）。

    Returns:
        解決した ``sub``。Bearer 形式でない、または空なら ``None``。
    """

    if not authorization or not authorization.lower().startswith("bearer "):
        return None

    token = authorization[len("Bearer ") :].strip()
    if not token:
        return None

    parts = token.split(".")
    if len(parts) == 3:
        payload_segment = parts[1]
        padding = "=" * (-len(payload_segment) % 4)
        try:
            claims = json.loads(base64.urlsafe_b64decode(payload_segment + padding))
        except (binascii.Error, ValueError, UnicodeDecodeError):
            logger.warning("JWT ペイロードを復号できないためトークン全体を sub とみなします")
        else:
            sub = claims.get("sub") if isinstance(claims, dict) else None
            if isinstance(sub, str) and sub:
                return sub

    return token


def cors_headers(origin: str | None) -> dict[str, str]:
    """リクエスト元に応じた CORS レスポンスヘッダを組み立てる。

    Args:
        origin: リクエストの ``Origin`` ヘッダ（未設定なら ``None``）。

    Returns:
        付与する CORS ヘッダ。許可対象外のオリジンなら空 dict。
    """

    if "*" in CORS_ALLOW_ORIGINS:
        allow_origin = "*"
    elif origin and origin in CORS_ALLOW_ORIGINS:
        allow_origin = origin
    else:
        return {}

    return {
        "Access-Control-Allow-Origin": allow_origin,
        "Access-Control-Allow-Headers": CORS_ALLOW_HEADERS,
        "Access-Control-Allow-Methods": CORS_ALLOW_METHODS,
        "Access-Control-Max-Age": CORS_MAX_AGE,
    }


def build_event(
    *,
    route: Route,
    path: str,
    query_string: str,
    path_parameters: dict[str, str],
    headers: dict[str, str],
    body: bytes,
    subject: str | None,
    source_ip: str,
) -> dict[str, Any]:
    """API Gateway HTTP API payload format 2.0 のイベントを組み立てる。

    Args:
        route: 一致したルート。
        path: リクエストパス。
        query_string: 生のクエリ文字列。
        path_parameters: パスパラメータ。
        headers: リクエストヘッダ（小文字キー）。
        body: リクエストボディ。
        subject: Authorizer が解決した ``sub``（認証不要ルートでは ``None``）。
        source_ip: 送信元 IP。

    Returns:
        Lambda へ渡すイベント dict。
    """

    query_parameters = {
        key: ",".join(values)
        for key, values in urllib.parse.parse_qs(query_string).items()
    }
    now = time.time()

    request_context: dict[str, Any] = {
        "accountId": "000000000000",
        "apiId": "local",
        "domainName": headers.get("host", "localhost"),
        "http": {
            "method": route.method,
            "path": path,
            "protocol": "HTTP/1.1",
            "sourceIp": source_ip,
            "userAgent": headers.get("user-agent", ""),
        },
        "requestId": str(uuid.uuid4()),
        "routeKey": route.route_key,
        "stage": "$default",
        "time": time.strftime("%d/%b/%Y:%H:%M:%S +0000", time.gmtime(now)),
        "timeEpoch": int(now * 1000),
    }

    # JWT Authorizer 適用ルートでは、検証済み claims を本番と同じ位置へ格納する。
    if route.require_jwt and subject is not None:
        request_context["authorizer"] = {
            "jwt": {"claims": {"sub": subject}, "scopes": None}
        }

    event: dict[str, Any] = {
        "version": "2.0",
        "routeKey": route.route_key,
        "rawPath": path,
        "rawQueryString": query_string,
        "headers": headers,
        "requestContext": request_context,
        "isBase64Encoded": False,
    }
    if query_parameters:
        event["queryStringParameters"] = query_parameters
    if path_parameters:
        event["pathParameters"] = path_parameters
    if body:
        event["body"] = body.decode("utf-8")

    return event


class ApiGatewayHandler(JsonRequestHandler):
    """HTTP リクエストを Lambda イベントへ変換して RIE へ中継するハンドラ。"""

    logger = logger

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler の規約
        """GET リクエストを処理する。"""

        self._handle("GET")

    def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler の規約
        """POST リクエストを処理する。"""

        self._handle("POST")

    def do_OPTIONS(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler の規約
        """CORS プリフライトへ 204 を返す（HTTP API の自動応答と同じ挙動）。"""

        headers = cors_headers(self.headers.get("Origin"))
        self.send_bytes(204, b"", "text/plain", headers)

    def _handle(self, method: str) -> None:
        """メソッド共通のルーティング・認可・中継処理を行う。

        Args:
            method: HTTP メソッド。
        """

        parsed = urllib.parse.urlsplit(self.path)
        path = urllib.parse.unquote(parsed.path)
        origin_headers = cors_headers(self.headers.get("Origin"))

        # ボディは分岐より前に必ず読み切る。HTTP/1.1 の keep-alive では、未読の
        # ボディが次のリクエストの先頭として解釈され、同じ接続を再利用する
        # クライアント（ブラウザや requests.Session）が壊れるため。
        try:
            body = self.read_body()
        except ValueError as exc:
            self.logger.warning("リクエストボディを読めません: %s", exc)
            self.send_bytes(
                400, b'{"message": "Bad Request"}', "application/json",
                {**origin_headers, "Connection": "close"},
            )
            self.close_connection = True
            return

        route, path_parameters = self._match_route(method, path)
        if route is None:
            self.send_json(404, {"message": "Not Found"}, origin_headers)
            return

        subject = resolve_subject(self.headers.get("Authorization"))
        if route.require_jwt and subject is None:
            # 実 API Gateway の JWT Authorizer と同じ応答形（本文は {"message": ...}）。
            self.send_json(401, {"message": "Unauthorized"}, origin_headers)
            return

        event = build_event(
            route=route,
            path=path,
            query_string=parsed.query,
            path_parameters=path_parameters,
            headers={k.lower(): v for k, v in self.headers.items()},
            body=body,
            subject=subject,
            source_ip=self.client_address[0],
        )

        try:
            result = lambda_client.invoke(event)
        except LambdaFunctionError as exc:
            self.logger.error("Lambda ハンドラが例外を送出しました: %s", exc)
            self.send_json(500, {"message": "Internal Server Error"}, origin_headers)
            return
        except LambdaInvocationError as exc:
            self.logger.error("Lambda を呼び出せません: %s", exc)
            self.send_json(502, {"message": "Bad Gateway"}, origin_headers)
            return

        self._send_lambda_response(result, origin_headers)

    @staticmethod
    def _match_route(method: str, path: str) -> tuple[Route | None, dict[str, str]]:
        """メソッドとパスに一致するルートを探す。

        Args:
            method: HTTP メソッド。
            path: リクエストパス。

        Returns:
            ``(一致したルート | None, パスパラメータ)`` のタプル。
        """

        for route in ROUTES:
            path_parameters = route.match(method, path)
            if path_parameters is not None:
                return route, path_parameters
        return None, {}

    def _send_lambda_response(
        self, result: Any, extra_headers: dict[str, str]
    ) -> None:
        """Lambda プロキシ統合の戻り値を HTTP 応答へ変換する。

        Args:
            result: ハンドラの戻り値。
            extra_headers: 追加で付与するヘッダ（CORS 等）。
        """

        if not isinstance(result, dict) or "statusCode" not in result:
            self.logger.error("Lambda プロキシ応答の形式が不正です: %r", result)
            self.send_json(502, {"message": "Bad Gateway"}, extra_headers)
            return

        status = int(result["statusCode"])
        raw_body = result.get("body") or ""
        body = (
            base64.b64decode(raw_body)
            if result.get("isBase64Encoded")
            else raw_body.encode("utf-8")
        )

        headers = dict(extra_headers)
        lambda_headers = result.get("headers") or {}
        content_type = "application/json"
        for name, value in lambda_headers.items():
            if name.lower() == "content-type":
                content_type = value
            elif name.lower() != "content-length":
                headers[name] = value

        self.send_bytes(status, body, content_type, headers)


if __name__ == "__main__":
    serve_forever(ApiGatewayHandler, LISTEN_PORT, logger)
