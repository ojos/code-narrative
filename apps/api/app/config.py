"""実行時設定を環境変数から読み込むモジュール。

テーブル名・キュー URL・リージョン等をハードコードせず、環境変数から
読み込む（shared-ai-rules §2 / SPEC の「環境変数から読む」方針）。
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache

from .constants import DEFAULT_GSI_NAME


@dataclass(frozen=True)
class Settings:
    """アプリケーションの実行時設定を保持するイミュータブルなデータクラス。

    Attributes:
        table_name: DynamoDB テーブル名（SPEC §4 ③ の ``CodeNarratives``）。
        queue_url: SQS キューの URL。
        aws_region: boto3 クライアントが利用する AWS リージョン。
        gsi_name: ユーザー別一覧に用いる GSI 名。
        default_list_limit: 一覧取得の既定ページサイズ。
        max_list_limit: 一覧取得で許可する最大ページサイズ。
    """

    table_name: str
    queue_url: str
    aws_region: str
    gsi_name: str
    default_list_limit: int
    max_list_limit: int


def _require_env(name: str) -> str:
    """必須環境変数を取得する。未設定なら明示的な例外を送出する。

    Args:
        name: 環境変数名。

    Returns:
        環境変数の値。

    Raises:
        RuntimeError: 環境変数が未設定の場合。
    """

    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"必須環境変数 {name} が設定されていません")
    return value


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """環境変数から設定を構築し、プロセス内でキャッシュして返す。

    Returns:
        現在の環境変数に基づく :class:`Settings` インスタンス。
    """

    return Settings(
        table_name=_require_env("DYNAMODB_TABLE_NAME"),
        queue_url=_require_env("SQS_QUEUE_URL"),
        aws_region=os.environ.get("AWS_REGION", "ap-northeast-1"),
        gsi_name=os.environ.get("DYNAMODB_GSI_NAME", DEFAULT_GSI_NAME),
        default_list_limit=int(os.environ.get("DEFAULT_LIST_LIMIT", "20")),
        max_list_limit=int(os.environ.get("MAX_LIST_LIMIT", "100")),
    )
