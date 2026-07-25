"""構造化（JSON）ログ出力を提供するモジュール。

CloudWatch Logs での検索性を高めるため、ログを 1 行 1 JSON で出力する。
``extra`` で渡された任意の属性（特に ``job_id``）を JSON に含める。
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any

# 標準 LogRecord が持つ属性名の集合。これら以外の属性を「追加フィールド」とみなす。
_RESERVED_ATTRS: frozenset[str] = frozenset(
    vars(logging.makeLogRecord({})).keys()
) | frozenset({"message", "asctime", "taskName"})


class JsonFormatter(logging.Formatter):
    """LogRecord を 1 行の JSON 文字列へ整形するフォーマッタ。

    ``logger.info(msg, extra={"job_id": ...})`` のように渡された追加属性を
    そのまま JSON のキーとして出力する。
    """

    def format(self, record: logging.LogRecord) -> str:
        """LogRecord を JSON 文字列へ変換する。

        Args:
            record: 整形対象のログレコード。

        Returns:
            JSON 形式のログ行。
        """

        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(
                record.created, tz=timezone.utc
            ).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        for key, value in record.__dict__.items():
            if key not in _RESERVED_ATTRS and not key.startswith("_"):
                payload[key] = value

        return json.dumps(payload, ensure_ascii=False, default=str)


def configure_logging(level: int = logging.INFO) -> None:
    """ルートロガーへ JSON フォーマッタを設定する。

    アプリケーション起動時に一度だけ呼び出す想定。既存ハンドラは置き換える。

    Args:
        level: ルートロガーへ設定するログレベル。
    """

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(level)


def get_logger(name: str) -> logging.Logger:
    """指定名のロガーを取得するヘルパー。

    Args:
        name: ロガー名（通常は ``__name__``）。

    Returns:
        設定済みのロガー。
    """

    return logging.getLogger(name)
