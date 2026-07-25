"""DynamoDB への変換ジョブレコードアクセスを担うリポジトリ。

SPEC §4 ③ のテーブル ``CodeNarratives`` に対する読み書きを、この 1 クラスに
集約する（責務分離: 永続化層）。boto3 の Table リソースを注入して用いる。
"""

from __future__ import annotations

from typing import Any

from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError

from ..constants import JobStatus
from ..logging_config import get_logger

logger = get_logger(__name__)


class RepositoryError(Exception):
    """永続化処理の失敗を表す例外。ルータ層で 5xx へ変換する。"""


class NarrativeRepository:
    """``CodeNarratives`` テーブルへの操作を提供するリポジトリ。

    Attributes:
        _table: boto3 の DynamoDB Table リソース。
        _gsi_name: ユーザー別一覧に用いる GSI 名。
    """

    def __init__(self, table: Any, gsi_name: str) -> None:
        """リポジトリを初期化する。

        Args:
            table: boto3 の DynamoDB Table リソース。
            gsi_name: ユーザー別一覧に用いる GSI 名。
        """

        self._table = table
        self._gsi_name = gsi_name

    def put_initial_record(
        self,
        *,
        job_id: str,
        user_id: str,
        repo_url: str,
        custom_prompt: str,
        model_id: str,
        created_at: str,
    ) -> None:
        """``status=queued`` の初期レコードを書き込む（SPEC §4 ① 手順 2）。

        同一 ``job_id`` が既存の場合は上書きしない（条件付き書き込み）。

        Args:
            job_id: 採番済みジョブ ID（UUID v4）。
            user_id: JWT の ``sub``。
            repo_url: 対象リポジトリ URL。
            custom_prompt: 世界観・スタイル指定。
            model_id: 使用モデル ID。
            created_at: 作成時刻（ISO8601）。

        Raises:
            RepositoryError: 書き込みに失敗した場合。
        """

        item = {
            "job_id": job_id,
            "user_id": user_id,
            "repo_url": repo_url,
            "custom_prompt": custom_prompt,
            "model_id": model_id,
            "status": JobStatus.QUEUED.value,
            "created_at": created_at,
            "updated_at": created_at,
        }
        try:
            self._table.put_item(
                Item=item,
                ConditionExpression="attribute_not_exists(job_id)",
            )
        except ClientError as exc:
            logger.error(
                "初期レコードの書き込みに失敗しました",
                extra={"job_id": job_id, "error": str(exc)},
            )
            raise RepositoryError("初期レコードの書き込みに失敗しました") from exc

    def get_by_job_id(self, job_id: str) -> dict[str, Any] | None:
        """``job_id`` でレコードを 1 件取得する。

        Args:
            job_id: 取得対象のジョブ ID。

        Returns:
            レコード（dict）。存在しなければ ``None``。

        Raises:
            RepositoryError: 取得に失敗した場合。
        """

        try:
            response = self._table.get_item(Key={"job_id": job_id})
        except ClientError as exc:
            logger.error(
                "レコード取得に失敗しました",
                extra={"job_id": job_id, "error": str(exc)},
            )
            raise RepositoryError("レコード取得に失敗しました") from exc

        item = response.get("Item")
        return item if isinstance(item, dict) else None

    def query_by_user(
        self,
        *,
        user_id: str,
        limit: int,
        exclusive_start_key: dict[str, Any] | None = None,
    ) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
        """GSI を用いてユーザーのジョブを新しい順に取得する（SPEC §4 ①）。

        Args:
            user_id: 対象ユーザーの ``sub``。
            limit: 取得件数の上限。
            exclusive_start_key: 継続取得の開始キー（任意）。

        Returns:
            ``(items, last_evaluated_key)`` のタプル。続きが無ければ
            ``last_evaluated_key`` は ``None``。

        Raises:
            RepositoryError: クエリに失敗した場合。
        """

        query_kwargs: dict[str, Any] = {
            "IndexName": self._gsi_name,
            "KeyConditionExpression": Key("user_id").eq(user_id),
            "ScanIndexForward": False,  # created_at の降順（新しい順）
            "Limit": limit,
        }
        if exclusive_start_key is not None:
            query_kwargs["ExclusiveStartKey"] = exclusive_start_key

        try:
            response = self._table.query(**query_kwargs)
        except ClientError as exc:
            logger.error(
                "ユーザー別一覧の取得に失敗しました",
                extra={"user_id": user_id, "error": str(exc)},
            )
            raise RepositoryError("ユーザー別一覧の取得に失敗しました") from exc

        items = response.get("Items", [])
        last_key = response.get("LastEvaluatedKey")
        return list(items), last_key if isinstance(last_key, dict) else None
