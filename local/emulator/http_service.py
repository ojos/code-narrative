"""ローカルエミュレータ各サービスが共有する最小 HTTP サーバ基盤。

`apigw` / `bedrock_stub` / `github_stub` / `frontend_server` は、いずれも
「JSON かバイナリを返す小さな HTTP サーバ」という同じ骨格を持つ。その共通部分
（ロギング設定・JSON 送受信・スレッド化サーバの起動）をここへ集約する。

本モジュールはローカル検証専用であり、本番の Lambda / API Gateway には含まれない。
"""

from __future__ import annotations

import json
import logging
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

# 1 リクエストで受理するボディの上限（DoS 対策ではなく、事故時の暴走防止）。
MAX_BODY_BYTES = 8 * 1024 * 1024


def configure_logging(service_name: str) -> logging.Logger:
    """サービス名付きのロガーを構成して返す。

    Args:
        service_name: ログに出す論理サービス名（例: ``apigw``）。

    Returns:
        構成済みのロガー。
    """

    logging.basicConfig(
        level=os.environ.get("LOCAL_LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    return logging.getLogger(service_name)


class JsonRequestHandler(BaseHTTPRequestHandler):
    """JSON の送受信ヘルパを備えた :class:`BaseHTTPRequestHandler` の基底クラス。

    サブクラスは ``do_GET`` / ``do_POST`` を実装し、``send_json`` /
    ``read_body`` を用いて応答する。

    Attributes:
        logger: サブクラスが差し替えるロガー。
    """

    # HTTP/1.1 を宣言し、Content-Length 付きの応答で keep-alive を成立させる。
    protocol_version = "HTTP/1.1"

    logger: logging.Logger = logging.getLogger("http_service")

    def read_body(self) -> bytes:
        """リクエストボディを ``Content-Length`` に従って読み取る。

        Returns:
            読み取ったボディ。ボディが無ければ空バイト列。

        Raises:
            ValueError: ``Content-Length`` が不正、または上限を超える場合。
        """

        raw_length = self.headers.get("Content-Length")
        if raw_length is None:
            return b""

        try:
            length = int(raw_length)
        except ValueError as exc:
            raise ValueError(f"Content-Length が不正です: {raw_length!r}") from exc

        if length < 0 or length > MAX_BODY_BYTES:
            raise ValueError(f"Content-Length が範囲外です: {length}")

        return self.rfile.read(length)

    def send_json(
        self,
        status: int,
        payload: Any,
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        """JSON 応答を送信する。

        Args:
            status: HTTP ステータスコード。
            payload: JSON へ直列化する値。
            extra_headers: 追加のレスポンスヘッダ。
        """

        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_bytes(status, body, "application/json", extra_headers)

    def send_bytes(
        self,
        status: int,
        body: bytes,
        content_type: str,
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        """任意のバイト列を応答として送信する。

        Args:
            status: HTTP ステータスコード。
            body: 応答ボディ。
            content_type: ``Content-Type`` ヘッダ値。
            extra_headers: 追加のレスポンスヘッダ。
        """

        self.send_response(status)
        # 204 と 1xx は本文を持たないため Content-Length を送らない（RFC 9110 6.4.1）。
        # 本文の長さが 0 であることは状態コード自体が示すので、keep-alive も壊れない。
        has_body = status != 204 and not (100 <= status < 200)
        if has_body:
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
        for name, value in (extra_headers or {}).items():
            self.send_header(name, value)
        self.end_headers()
        if has_body and self.command != "HEAD":
            self.wfile.write(body)

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        """アクセスログを標準のロガーへ流す（既定の stderr 直書きを止める）。

        Args:
            format: 書式文字列。
            args: 書式引数。
        """

        self.logger.debug("%s - %s", self.address_string(), format % args)


def serve_forever(
    handler_class: type[BaseHTTPRequestHandler],
    port: int,
    logger: logging.Logger,
) -> None:
    """スレッド化 HTTP サーバを起動し、停止シグナルまで待ち受ける。

    Args:
        handler_class: リクエストハンドラのクラス。
        port: 待ち受けポート。
        logger: 起動ログを出すロガー。
    """

    server = ThreadingHTTPServer(("0.0.0.0", port), handler_class)
    logger.info("listening on port %d", port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:  # pragma: no cover - コンテナ停止時の正常経路
        logger.info("shutting down")
    finally:
        server.server_close()


def env_int(name: str, default: int) -> int:
    """整数の環境変数を読む。未設定・不正なら既定値を返す。

    Args:
        name: 環境変数名。
        default: 既定値。

    Returns:
        解釈した整数値。
    """

    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError:
        logging.getLogger("http_service").warning(
            "環境変数 %s が整数として不正（%r）のため既定値 %d を使用します",
            name,
            raw,
            default,
        )
        return default
