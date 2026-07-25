"""時刻に関するユーティリティ。

ISO8601（UTC）文字列生成を一箇所に集約する（SPEC §4 ③ の
``created_at`` / ``updated_at`` はいずれも ISO8601 文字列）。
"""

from __future__ import annotations

from datetime import datetime, timezone


def utcnow_iso() -> str:
    """現在時刻を UTC の ISO8601 文字列（末尾 ``Z``）で返す。

    Returns:
        例: ``2026-07-25T00:00:00.123456Z``。GSI のレンジキーとして
        辞書順ソートが時系列順と一致するようマイクロ秒まで含める。
    """

    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
