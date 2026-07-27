"""Lambda SQS イベントソースマッピング (ESM) のローカルエミュレータ。

`terraform/modules/worker/lambda.tf` の ``aws_lambda_event_source_mapping`` を
写し取り、次を再現する。

- ``batch_size`` 件ずつのロングポーリング受信。
- ``events.SQSEvent`` 形式のイベント生成と RIE 経由のハンドラ呼び出し。
- ``ReportBatchItemFailures``: 応答の ``batchItemFailures`` に含まれない
  メッセージのみ削除し、含まれるものは削除せず可視性タイムアウト経過後に再配信させる。
- ハンドラ自体が例外を送出した場合はバッチ全体を未削除のままにする。

削除しなかったメッセージは、キュー側の ``maxReceiveCount`` 超過で DLQ へ退避する
（redrive はキュー実装が担うため、ここでは何もしない）。

本モジュールはローカル検証専用であり、本番の Lambda には含まれない。
"""

from __future__ import annotations

import hashlib
import os
import signal
import sys
import time
from types import FrameType
from typing import Any

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from http_service import configure_logging, env_int
from lambda_rie import LambdaFunctionError, LambdaInvocationError, LambdaRieClient

logger = configure_logging("esm")

# --- 設定（環境変数） ---

QUEUE_URL = os.environ["SQS_QUEUE_URL"]
AWS_REGION = os.environ.get("AWS_REGION", "ap-northeast-1")
LAMBDA_ENDPOINT = os.environ.get("LOCAL_WORKER_LAMBDA_ENDPOINT", "http://worker:8080")
# 本番 worker のタイムアウト（terraform: local.worker_timeout = 300）に合わせる。
LAMBDA_TIMEOUT_SECONDS = env_int("LOCAL_WORKER_LAMBDA_TIMEOUT", 300)
# terraform: modules/worker の batch_size 既定値。
BATCH_SIZE = env_int("LOCAL_ESM_BATCH_SIZE", 1)
# ロングポーリングの待機秒数。空ポーリングの CPU 消費を抑える。
WAIT_TIME_SECONDS = env_int("LOCAL_ESM_WAIT_TIME_SECONDS", 2)
# 受信エラー時の再試行間隔（秒）。
RETRY_INTERVAL_SECONDS = 1.0

lambda_client = LambdaRieClient(LAMBDA_ENDPOINT, LAMBDA_TIMEOUT_SECONDS)

# 実行中フラグ。SIGTERM/SIGINT で False にしてループを抜ける。
_running = True


def _handle_signal(signum: int, frame: FrameType | None) -> None:
    """停止シグナルを受けてポーリングループの終了を指示する。

    Args:
        signum: シグナル番号。
        frame: シグナル発生時のスタックフレーム（未使用）。
    """

    global _running
    logger.info("シグナル %d を受信しました。ポーリングを停止します", signum)
    _running = False


def build_sqs_event(messages: list[dict[str, Any]], queue_url: str) -> dict[str, Any]:
    """受信メッセージ群から ``events.SQSEvent`` 形式のイベントを組み立てる。

    Args:
        messages: ``receive_message`` が返した Messages。
        queue_url: 送信元キューの URL。

    Returns:
        Lambda へ渡すイベント dict。
    """

    queue_name = queue_url.rstrip("/").rsplit("/", 1)[-1]
    event_source_arn = f"arn:aws:sqs:{AWS_REGION}:000000000000:{queue_name}"

    records = []
    for message in messages:
        body = message.get("Body", "")
        records.append(
            {
                "messageId": message["MessageId"],
                "receiptHandle": message["ReceiptHandle"],
                "body": body,
                "attributes": message.get("Attributes", {}),
                "messageAttributes": message.get("MessageAttributes", {}),
                "md5OfBody": message.get(
                    "MD5OfBody", hashlib.md5(body.encode("utf-8")).hexdigest()
                ),
                "eventSource": "aws:sqs",
                "eventSourceARN": event_source_arn,
                "awsRegion": AWS_REGION,
            }
        )

    return {"Records": records}


def failed_message_ids(response: Any, messages: list[dict[str, Any]]) -> set[str]:
    """ハンドラ応答から「削除してはいけない」メッセージ ID を求める。

    ``ReportBatchItemFailures`` の契約に従い、``batchItemFailures`` に列挙された
    ``itemIdentifier`` のみを失敗とみなす。応答が期待形でない場合は、取りこぼしを
    避けるためバッチ全体を失敗（未削除）として扱う。

    Args:
        response: ハンドラの戻り値。
        messages: 送信したメッセージ群。

    Returns:
        削除対象から除外するメッセージ ID の集合。
    """

    if response is None:
        return set()

    if not isinstance(response, dict):
        logger.error("ハンドラ応答が dict ではありません: %r。バッチ全体を再配信します", response)
        return {message["MessageId"] for message in messages}

    failures = response.get("batchItemFailures")
    if failures is None:
        return set()

    if not isinstance(failures, list):
        logger.error(
            "batchItemFailures が list ではありません: %r。バッチ全体を再配信します", failures
        )
        return {message["MessageId"] for message in messages}

    identifiers = set()
    for failure in failures:
        if isinstance(failure, dict) and isinstance(failure.get("itemIdentifier"), str):
            identifiers.add(failure["itemIdentifier"])
        else:
            logger.error(
                "batchItemFailures の要素が不正です: %r。バッチ全体を再配信します", failure
            )
            return {message["MessageId"] for message in messages}
    return identifiers


def delete_messages(
    sqs: Any, queue_url: str, messages: list[dict[str, Any]], failed_ids: set[str]
) -> None:
    """失敗として報告されなかったメッセージをキューから削除する。

    Args:
        sqs: boto3 の SQS クライアント。
        queue_url: 対象キューの URL。
        messages: 受信したメッセージ群。
        failed_ids: 削除対象から除外するメッセージ ID。
    """

    entries = [
        {"Id": str(index), "ReceiptHandle": message["ReceiptHandle"]}
        for index, message in enumerate(messages)
        if message["MessageId"] not in failed_ids
    ]
    if not entries:
        return

    try:
        result = sqs.delete_message_batch(QueueUrl=queue_url, Entries=entries)
    except (BotoCoreError, ClientError) as exc:
        # 削除に失敗しても可視性タイムアウト経過後に再配信される（at-least-once）。
        logger.error("メッセージ削除に失敗しました: %s", exc)
        return

    for failure in result.get("Failed", []):
        logger.error("メッセージ削除が個別に失敗しました: %s", failure)


def process_batch(sqs: Any, messages: list[dict[str, Any]]) -> None:
    """1 バッチ分のメッセージをハンドラへ渡し、結果に応じて削除する。

    Args:
        sqs: boto3 の SQS クライアント。
        messages: 受信したメッセージ群。
    """

    event = build_sqs_event(messages, QUEUE_URL)
    message_ids = [message["MessageId"] for message in messages]

    try:
        response = lambda_client.invoke(event)
    except LambdaFunctionError as exc:
        # 実 ESM と同じく、関数エラー時はバッチ全体を再配信対象にする。
        logger.error("worker ハンドラが例外を送出しました（バッチ全体を再配信）: %s", exc)
        return
    except LambdaInvocationError as exc:
        logger.error("worker を呼び出せません（バッチ全体を再配信）: %s", exc)
        return

    failed_ids = failed_message_ids(response, messages)
    if failed_ids:
        logger.warning("再配信対象のメッセージ: %s", sorted(failed_ids))

    delete_messages(sqs, QUEUE_URL, messages, failed_ids)
    logger.info(
        "バッチ処理完了: received=%d failed=%d ids=%s",
        len(messages),
        len(failed_ids),
        message_ids,
    )


def main() -> int:
    """SQS をロングポーリングし続けるメインループ。

    Returns:
        プロセスの終了コード。
    """

    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    # ロングポーリングの待機中に読み取りタイムアウトで切れないよう余裕を持たせる。
    sqs = boto3.client(
        "sqs",
        region_name=AWS_REGION,
        config=Config(read_timeout=WAIT_TIME_SECONDS + 20, retries={"max_attempts": 3}),
    )
    logger.info(
        "ポーリング開始: queue=%s batch_size=%d lambda=%s",
        QUEUE_URL,
        BATCH_SIZE,
        LAMBDA_ENDPOINT,
    )

    while _running:
        try:
            response = sqs.receive_message(
                QueueUrl=QUEUE_URL,
                MaxNumberOfMessages=BATCH_SIZE,
                WaitTimeSeconds=WAIT_TIME_SECONDS,
                AttributeNames=["All"],
                MessageAttributeNames=["All"],
            )
        except (BotoCoreError, ClientError) as exc:
            # 受信自体が失敗し続ける場合に CPU を焼かないよう、間隔を空けて再試行する。
            logger.error("メッセージ受信に失敗しました: %s", exc)
            time.sleep(RETRY_INTERVAL_SECONDS)
            continue

        messages = response.get("Messages", [])
        if messages:
            process_batch(sqs, messages)

    logger.info("ポーリングを終了しました")
    return 0


if __name__ == "__main__":
    sys.exit(main())
