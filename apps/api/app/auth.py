"""認証ユーザー（JWT の ``sub``）を解決する依存関係を提供するモジュール。

本番の正規経路では、API Gateway (HTTP API) の JWT Authorizer が署名検証済み
トークンの claims を Lambda イベントの
``requestContext.authorizer.jwt.claims`` に格納する。この検証済み ``sub`` が
あれば常にそれを用いる。

検証済み claims が無い場合の生 ``Authorization: Bearer`` の復号（署名の真正性を
検証しないフォールバック）は、既定では無効であり 401 とする。環境変数
``AUTH_ALLOW_UNVERIFIED_JWT=true`` を設定したローカル/テスト環境でのみ有効化
される。署名の暗号検証（JWKS）は本モジュールのスコープ外であり、本番では
このフォールバックに依存しない。
"""

from __future__ import annotations

import base64
import binascii
import json
from typing import Any

from fastapi import Depends, HTTPException, Request, status

from .config import Settings, get_settings
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
    """JWT のペイロード部から ``sub`` を取り出すフォールバック。

    このフォールバックは署名検証を行わず（完全な JWKS 検証は本モジュールの
    スコープ外）、ペイロードから ``sub`` を抽出するのみである。本来は API
    Gateway の JWT Authorizer が署名検証済みトークンを渡す前提だが、Authorizer
    を経由せず到達した場合（Function URL 露出・直接 Invoke 等）の ``sub`` 詐称を
    最小限抑止するため、``alg: none``（および署名部が空のトークン）は拒否する。

    Args:
        token: ``Bearer`` の後に続く JWT 文字列。

    Returns:
        ペイロード中の ``sub``。取り出せない、または ``alg: none`` 等で
        拒否した場合は ``None``。
    """

    parts = token.split(".")
    if len(parts) != 3:
        return None

    header_segment, payload_segment, signature_segment = parts

    # 署名部が空、すなわち "unsecured" JWT（alg:none 相当）は拒否する。
    if not signature_segment:
        logger.warning("署名なし JWT を拒否しました")
        return None

    # ヘッダの alg が none の場合は拒否する。
    header_padding = "=" * (-len(header_segment) % 4)
    try:
        header_decoded = base64.urlsafe_b64decode(header_segment + header_padding)
        header = json.loads(header_decoded)
    except (binascii.Error, ValueError, UnicodeDecodeError) as exc:
        logger.warning("JWT ヘッダの復号に失敗しました", extra={"error": str(exc)})
        return None

    alg = header.get("alg") if isinstance(header, dict) else None
    if not isinstance(alg, str) or alg.strip().lower() == "none":
        logger.warning("alg:none または不正な alg の JWT を拒否しました")
        return None

    padding = "=" * (-len(payload_segment) % 4)
    try:
        decoded = base64.urlsafe_b64decode(payload_segment + padding)
        data = json.loads(decoded)
    except (binascii.Error, ValueError, UnicodeDecodeError) as exc:
        logger.warning("JWT ペイロードの復号に失敗しました", extra={"error": str(exc)})
        return None

    sub = data.get("sub") if isinstance(data, dict) else None
    return sub if isinstance(sub, str) and sub else None


def get_current_user_id(
    request: Request,
    settings: Settings = Depends(get_settings),
) -> str:
    """認証済みユーザーの ``sub``（=``user_id``）を解決する FastAPI 依存関係。

    優先順位:

    1. API Gateway JWT Authorizer が格納した検証済み claims の ``sub``
       （本番の正規経路。常にこれを用いる）。
    2. 上記が無く、かつ ``AUTH_ALLOW_UNVERIFIED_JWT=true`` の場合のみ、
       生 Bearer トークンの未検証復号による ``sub``（ローカル/テスト用途）。

    既定（``AUTH_ALLOW_UNVERIFIED_JWT`` 未設定/false）では未検証フォールバックを
    行わず、検証済み claims が無ければ 401 とする。これは、API Gateway を経由せず
    Lambda に到達した場合（Function URL 露出・直接 Invoke 等）に、ダミー署名付き
    トークンで任意の ``sub`` へなりすまされることを防ぐため。

    Args:
        request: FastAPI のリクエストオブジェクト。
        settings: 実行時設定。

    Returns:
        認証ユーザーの ``sub``。

    Raises:
        HTTPException: ``sub`` を解決できない場合は 401 Unauthorized。
    """

    sub = _extract_sub_from_event(request)
    if sub:
        return sub

    if settings.auth_allow_unverified_jwt:
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
