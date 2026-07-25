"""認証フォールバック（Authorization ヘッダ復号）の単体テスト。

API Gateway JWT Authorizer を経由せず到達した場合の sub 詐称を抑止するため、
``alg:none`` および署名なしトークンが拒否される（401 になる）ことを検証する。
"""

from __future__ import annotations

import base64
import json
from typing import Any

from fastapi.testclient import TestClient


def _b64url(payload: dict[str, Any]) -> str:
    """dict を JWT セグメント用の URL セーフ Base64（パディング無し）へ変換する。

    Args:
        payload: エンコード対象。

    Returns:
        パディングを除いた URL セーフ Base64 文字列。
    """

    raw = json.dumps(payload).encode("utf-8")
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _token(header: dict[str, Any], body: dict[str, Any], signature: str) -> str:
    """任意のヘッダ・ペイロード・署名部から JWT 風トークンを組み立てる。

    Args:
        header: JWT ヘッダ。
        body: JWT ペイロード。
        signature: 署名部（空文字も可）。

    Returns:
        ``header.body.signature`` 形式のトークン。
    """

    return f"{_b64url(header)}.{_b64url(body)}.{signature}"


def test_alg_none_token_is_rejected(
    client: TestClient,
    valid_payload: dict[str, str],
) -> None:
    """alg:none の自作トークンは sub を採用せず 401 になる。"""

    token = _token({"alg": "none", "typ": "JWT"}, {"sub": "attacker"}, "sig")
    response = client.post(
        "/api/v1/narratives",
        json=valid_payload,
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 401


def test_unsigned_token_is_rejected(
    client: TestClient,
    valid_payload: dict[str, str],
) -> None:
    """署名部が空のトークンは sub を採用せず 401 になる。"""

    token = _token({"alg": "RS256", "typ": "JWT"}, {"sub": "attacker"}, "")
    response = client.post(
        "/api/v1/narratives",
        json=valid_payload,
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 401


def test_signed_alg_token_is_accepted(
    client: TestClient,
    valid_payload: dict[str, str],
) -> None:
    """alg が none 以外かつ署名部が非空なら sub を採用し 202 になる。

    （署名の暗号検証は本フォールバックのスコープ外。alg:none 拒否のみを担保）。
    """

    token = _token({"alg": "RS256", "typ": "JWT"}, {"sub": "user-1"}, "dummy")
    response = client.post(
        "/api/v1/narratives",
        json=valid_payload,
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 202
