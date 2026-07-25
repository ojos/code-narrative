"""一覧取得のページネーショントークンを扱うユーティリティ。

DynamoDB の ``LastEvaluatedKey``（dict）を不透明な ``next_token`` 文字列へ
相互変換する。トークンは URL セーフな Base64 でエンコードした JSON。
"""

from __future__ import annotations

import base64
import binascii
import json
from typing import Any


def encode_next_token(last_evaluated_key: dict[str, Any]) -> str:
    """DynamoDB の LastEvaluatedKey を next_token 文字列へエンコードする。

    Args:
        last_evaluated_key: ``query`` が返す継続キー。

    Returns:
        URL セーフ Base64 でエンコードした不透明トークン。
    """

    raw = json.dumps(last_evaluated_key, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii")


def decode_next_token(token: str) -> dict[str, Any]:
    """next_token 文字列を DynamoDB の ExclusiveStartKey へデコードする。

    Args:
        token: :func:`encode_next_token` が生成したトークン。

    Returns:
        ``query`` の ``ExclusiveStartKey`` に渡せる dict。

    Raises:
        ValueError: トークンが不正で復号・解釈できない場合。
    """

    try:
        raw = base64.urlsafe_b64decode(token.encode("ascii"))
        decoded = json.loads(raw)
    except (binascii.Error, ValueError, UnicodeDecodeError) as exc:
        raise ValueError("next_token の形式が不正です") from exc

    if not isinstance(decoded, dict):
        raise ValueError("next_token の内容が不正です")
    return decoded
