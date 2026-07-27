"""ローカル環境の DynamoDB テーブルと SQS キューを冪等に用意する初期化ジョブ。

`terraform/modules/dynamodb` のテーブル定義（ハッシュキー ``job_id``、GSI
``user_id`` + ``created_at``、射影 ALL）をローカルの DynamoDB Local へ写す。
SQS 側のキューと DLQ・redrive は ElasticMQ の設定ファイルが宣言的に作るため、
ここでは存在確認のみ行う。

同じ入力で何度実行しても壊れず、既に正しい状態なら何もしない（冪等）。

本モジュールはローカル検証専用であり、本番には含まれない。
"""

from __future__ import annotations

import os
import sys
import time
from collections.abc import Callable
from typing import Any

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from http_service import configure_logging, env_int

logger = configure_logging("init")

TABLE_NAME = os.environ["DYNAMODB_TABLE"]
GSI_NAME = os.environ.get("DYNAMODB_GSI_NAME", "user_id-created_at-index")
QUEUE_URL = os.environ["SQS_QUEUE_URL"]
DLQ_URL = os.environ["SQS_DLQ_URL"]
AWS_REGION = os.environ.get("AWS_REGION", "ap-northeast-1")

# 依存サービスの起動待ち上限（秒）と再試行間隔（秒）。
READY_TIMEOUT_SECONDS = env_int("LOCAL_INIT_TIMEOUT_SECONDS", 90)
RETRY_INTERVAL_SECONDS = 1.0


def create_table(dynamodb: Any) -> None:
    """ジョブテーブルを作成する。既に存在すれば何もしない。

    Args:
        dynamodb: boto3 の DynamoDB クライアント。
    """

    try:
        dynamodb.create_table(
            TableName=TABLE_NAME,
            BillingMode="PAY_PER_REQUEST",
            KeySchema=[{"AttributeName": "job_id", "KeyType": "HASH"}],
            AttributeDefinitions=[
                {"AttributeName": "job_id", "AttributeType": "S"},
                {"AttributeName": "user_id", "AttributeType": "S"},
                {"AttributeName": "created_at", "AttributeType": "S"},
            ],
            GlobalSecondaryIndexes=[
                {
                    "IndexName": GSI_NAME,
                    "KeySchema": [
                        {"AttributeName": "user_id", "KeyType": "HASH"},
                        {"AttributeName": "created_at", "KeyType": "RANGE"},
                    ],
                    "Projection": {"ProjectionType": "ALL"},
                }
            ],
        )
        logger.info("テーブル %s を作成しました", TABLE_NAME)
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") == "ResourceInUseException":
            logger.info("テーブル %s は既に存在します", TABLE_NAME)
            return
        raise


def wait_for_table_active(dynamodb: Any) -> None:
    """テーブルと GSI が ACTIVE になるまで待機する。

    Args:
        dynamodb: boto3 の DynamoDB クライアント。

    Raises:
        TimeoutError: 制限時間内に ACTIVE にならなかった場合。
    """

    deadline = time.monotonic() + READY_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        description = dynamodb.describe_table(TableName=TABLE_NAME)["Table"]
        indexes = description.get("GlobalSecondaryIndexes", [])
        if description["TableStatus"] == "ACTIVE" and all(
            index["IndexStatus"] == "ACTIVE" for index in indexes
        ):
            logger.info("テーブル %s と GSI が ACTIVE になりました", TABLE_NAME)
            return
        time.sleep(RETRY_INTERVAL_SECONDS)

    raise TimeoutError(f"テーブル {TABLE_NAME} が制限時間内に ACTIVE になりませんでした")


def verify_queues(sqs: Any) -> None:
    """キューと DLQ が存在し、redrive が設定されていることを確認する。

    Args:
        sqs: boto3 の SQS クライアント。

    Raises:
        RuntimeError: キューが存在しない、または redrive が未設定の場合。
    """

    for url in (QUEUE_URL, DLQ_URL):
        try:
            sqs.get_queue_attributes(QueueUrl=url, AttributeNames=["QueueArn"])
        except ClientError as exc:
            raise RuntimeError(f"キュー {url} を参照できません: {exc}") from exc

    attributes = sqs.get_queue_attributes(
        QueueUrl=QUEUE_URL, AttributeNames=["RedrivePolicy"]
    ).get("Attributes", {})
    if "RedrivePolicy" not in attributes:
        raise RuntimeError(
            f"キュー {QUEUE_URL} に redrive が設定されていません。"
            "local/elasticmq/elasticmq.conf.template を確認してください"
        )
    logger.info("キューと DLQ を確認しました: %s", attributes["RedrivePolicy"])


def wait_until_ready(
    client_factory: Callable[[], Any], probe: Callable[[Any], Any], label: str
) -> Any:
    """依存サービスが応答するまで待機し、応答したクライアントを返す。

    Args:
        client_factory: boto3 クライアントを生成する関数。
        probe: クライアントを受け取り、疎通確認を行う関数。
        label: ログに出すサービス名。

    Returns:
        疎通確認済みのクライアント。

    Raises:
        TimeoutError: 制限時間内に応答しなかった場合。
    """

    client = client_factory()
    deadline = time.monotonic() + READY_TIMEOUT_SECONDS
    last_error: Exception | None = None

    while time.monotonic() < deadline:
        try:
            probe(client)
        except (BotoCoreError, ClientError) as exc:
            last_error = exc
            time.sleep(RETRY_INTERVAL_SECONDS)
        else:
            logger.info("%s へ疎通しました", label)
            return client

    raise TimeoutError(f"{label} へ疎通できませんでした: {last_error}")


def main() -> int:
    """初期化を実行する。

    Returns:
        プロセスの終了コード。
    """

    try:
        dynamodb = wait_until_ready(
            lambda: boto3.client("dynamodb", region_name=AWS_REGION),
            lambda client: client.list_tables(),
            "DynamoDB Local",
        )
        sqs = wait_until_ready(
            lambda: boto3.client("sqs", region_name=AWS_REGION),
            lambda client: client.get_queue_attributes(
                QueueUrl=QUEUE_URL, AttributeNames=["QueueArn"]
            ),
            "SQS (ElasticMQ)",
        )

        create_table(dynamodb)
        wait_for_table_active(dynamodb)
        verify_queues(sqs)
    except (BotoCoreError, ClientError, RuntimeError, TimeoutError) as exc:
        logger.error("初期化に失敗しました: %s", exc)
        return 1

    logger.info("初期化が完了しました")
    return 0


if __name__ == "__main__":
    sys.exit(main())
