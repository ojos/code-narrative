"""認証ユーザー（JWT の ``sub``）を解決する依存関係を提供するモジュール。

API Gateway (HTTP API) の JWT Authorizer が検証済みトークンの claims を
Lambda イベントの ``requestContext.authorizer.jwt.claims`` に格納する前提。
その値を優先的に用い、無い場合は多層防御として ``Authorization: Bearer``
ヘッダのペイロードを（署名検証済み前提で）復号して ``sub`` を取得する。
"""

from __future__ import annotations

import base64
import binascii
import json
from typing import Any

from fastapi import HTTPException, Request, status

from .logging_config import get_logger

logger = get_logger(__name__)


def _extract_sub_from_event(request: Request) -> str | None:
    """Mangum が渡す Lambda イベントの JWT claims から ``sub`` を取得する。

    Args:
        request: FastAPI のリクエストオブジェクト。

    Returns:
        取得できた ``sub``。取得できなければ ``None``。
    """

    event: Any = request.scope.get("aws.event")
    if not isinstance(event, dict):
        return None

    try:
        claims = event["requestContext"]["authorizer"]["jwt"]["claims"]
    except (KeyError, TypeError):
        return None

    sub = claims.get("sub") if isinstance(claims, dict) else None
    return sub if isinstance(sub, str) and sub else None


def _decode_unverified_sub(token: str) -> str | None:
    """JWT のペイロード部を署名検証せずに復号し ``sub`` を取り出す。

    API Gateway の JWT Authorizer が既に署名検証済みである前提の
    多層防御用フォールバック（ローカル・テスト経路でも利用）。

    Args:
        token: ``Bearer`` の後に続く JWT 文字列。

    Returns:
        ペイロード中の ``sub``。取り出せなければ ``None``。
    """

    parts = token.split(".")
    if len(parts) != 3:
        return None

    payload_segment = parts[1]
    padding = "=" * (-len(payload_segment) % 4)
    try:
        decoded = base64.urlsafe_b64decode(payload_segment + padding)
        data = json.loads(decoded)
    except (binascii.Error, ValueError, UnicodeDecodeError) as exc:
        logger.warning("JWT ペイロードの復号に失敗しました", extra={"error": str(exc)})
        return None

    sub = data.get("sub") if isinstance(data, dict) else None
    return sub if isinstance(sub, str) and sub else None


def get_current_user_id(request: Request) -> str:
    """認証済みユーザーの ``sub``（=``user_id``）を解決する FastAPI 依存関係。

    Args:
        request: FastAPI のリクエストオブジェクト。

    Returns:
        認証ユーザーの ``sub``。

    Raises:
        HTTPException: ``sub`` を解決できない場合は 401 Unauthorized。
    """

    sub = _extract_sub_from_event(request)
    if sub:
        return sub

    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[len("Bearer ") :].strip()
        sub = _decode_unverified_sub(token)
        if sub:
            return sub

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="認証情報が不正です",
    )
