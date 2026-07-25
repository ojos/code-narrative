"""SQS へのジョブメッセージ投入を担うサービス。

SPEC §4 ① 手順 3 のエンキュー処理をこの 1 クラスに集約する（責務分離）。
boto3 の SQS クライアントを注入して用いる。
"""

from __future__ import annotations

import json
from typing import Any

from botocore.exceptions import ClientError

from ..logging_config import get_logger

logger = get_logger(__name__)


class QueueError(Exception):
    """SQS への送信失敗を表す例外。ルータ層で 5xx へ変換する。"""


class QueueService:
    """SQS 標準キューへ変換ジョブを投入するサービス。

    Attributes:
        _client: boto3 の SQS クライアント。
        _queue_url: 送信先キューの URL。
    """

    def __init__(self, client: Any, queue_url: str) -> None:
        """サービスを初期化する。

        Args:
            client: boto3 の SQS クライアント。
            queue_url: 送信先キューの URL。
        """

        self._client = client
        self._queue_url = queue_url

    def enqueue_job(
        self,
        *,
        job_id: str,
        repo_url: str,
        custom_prompt: str,
        model_id: str,
    ) -> None:
        """ワーカーが処理するジョブメッセージを SQS へ送信する。

        メッセージボディにはワーカー（SPEC §4 ②）が必要とする
        ``job_id`` / ``repo_url`` / ``custom_prompt`` / ``model_id`` を含める。

        Args:
            job_id: ジョブ ID。
            repo_url: 対象リポジトリ URL。
            custom_prompt: 世界観・スタイル指定。
            model_id: 使用モデル ID。

        Raises:
            QueueError: 送信に失敗した場合。
        """

        body = json.dumps(
            {
                "job_id": job_id,
                "repo_url": repo_url,
                "custom_prompt": custom_prompt,
                "model_id": model_id,
            },
            ensure_ascii=False,
        )
        try:
            self._client.send_message(QueueUrl=self._queue_url, MessageBody=body)
        except ClientError as exc:
            logger.error(
                "SQS へのエンキューに失敗しました",
                extra={"job_id": job_id, "error": str(exc)},
            )
            raise QueueError("SQS へのエンキューに失敗しました") from exc
