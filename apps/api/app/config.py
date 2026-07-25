"""実行時設定を環境変数から読み込むモジュール。

テーブル名・キュー URL・リージョン等をハードコードせず、環境変数から
読み込む（shared-ai-rules §2 / SPEC の「環境変数から読む」方針）。
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache

from .constants import ALLOWED_MODEL_IDS, DEFAULT_GSI_NAME


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
        allowed_model_ids: model_id バリデーションで許可するモデル ID 集合。
            env ``MODEL_WHITELIST``（terraform 注入）から構築し、未設定/空なら
            :data:`constants.ALLOWED_MODEL_IDS` をフォールバックとする。
        auth_allow_unverified_jwt: 署名未検証の Bearer フォールバックを許可するか。
            本番では常に false（既定）。ローカル/テスト用途でのみ true にする。
    """

    table_name: str
    queue_url: str
    aws_region: str
    gsi_name: str
    default_list_limit: int
    max_list_limit: int
    allowed_model_ids: frozenset[str]
    auth_allow_unverified_jwt: bool


def _parse_bool(value: str | None) -> bool:
    """環境変数の文字列を真偽値へ明示的に解釈する。

    ``"1"`` / ``"true"`` / ``"yes"``（大小・前後空白無視）のみ true とし、
    未設定・空・その他の値はすべて false とする（安全側の既定）。

    Args:
        value: 環境変数の値（未設定なら ``None``）。

    Returns:
        解釈した真偽値。
    """

    if value is None:
        return False
    return value.strip().lower() in {"1", "true", "yes"}


def _parse_model_whitelist(value: str | None) -> frozenset[str]:
    """env ``MODEL_WHITELIST`` を許可モデル ID 集合へ解釈する。

    カンマ区切りの各要素を前後空白トリムし、空要素は除去する。未設定・空・
    トリム後に要素が残らない場合は :data:`constants.ALLOWED_MODEL_IDS` を
    フォールバックとして返す（本番 env 不備でも既定の東京 2 モデルで動作継続）。

    Args:
        value: 環境変数 ``MODEL_WHITELIST`` の値（未設定なら ``None``）。

    Returns:
        許可モデル ID の集合。
    """

    if value is None:
        return ALLOWED_MODEL_IDS
    ids = frozenset(item.strip() for item in value.split(",") if item.strip())
    return ids or ALLOWED_MODEL_IDS


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
        table_name=_require_env("DYNAMODB_TABLE"),
        queue_url=_require_env("SQS_QUEUE_URL"),
        aws_region=os.environ.get("AWS_REGION", "ap-northeast-1"),
        gsi_name=os.environ.get("DYNAMODB_GSI_NAME", DEFAULT_GSI_NAME),
        default_list_limit=int(os.environ.get("DEFAULT_LIST_LIMIT", "20")),
        max_list_limit=int(os.environ.get("MAX_LIST_LIMIT", "100")),
        allowed_model_ids=_parse_model_whitelist(
            os.environ.get("MODEL_WHITELIST")
        ),
        auth_allow_unverified_jwt=_parse_bool(
            os.environ.get("AUTH_ALLOW_UNVERIFIED_JWT")
        ),
    )
