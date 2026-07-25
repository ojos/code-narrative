"""FastAPI の依存性注入プロバイダを定義するモジュール。

boto3 リソース/クライアントの生成を一箇所に集約し、リポジトリ・キュー・
サービスを組み立てる。テストでは ``app.dependency_overrides`` で差し替える。
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

import boto3
from fastapi import Depends

from .config import Settings, get_settings
from .repositories.narrative_repository import NarrativeRepository
from .services.narrative_service import NarrativeService
from .services.queue_service import QueueService


@lru_cache(maxsize=1)
def _get_dynamodb_table(region: str, table_name: str) -> Any:
    """boto3 の DynamoDB Table リソースを生成・キャッシュする。

    Args:
        region: AWS リージョン。
        table_name: テーブル名。

    Returns:
        DynamoDB Table リソース。
    """

    resource = boto3.resource("dynamodb", region_name=region)
    return resource.Table(table_name)


@lru_cache(maxsize=1)
def _get_sqs_client(region: str) -> Any:
    """boto3 の SQS クライアントを生成・キャッシュする。

    Args:
        region: AWS リージョン。

    Returns:
        SQS クライアント。
    """

    return boto3.client("sqs", region_name=region)


def get_repository(
    settings: Settings = Depends(get_settings),
) -> NarrativeRepository:
    """DynamoDB リポジトリを提供する依存関係。

    Args:
        settings: 実行時設定。

    Returns:
        構築済み :class:`NarrativeRepository`。
    """

    table = _get_dynamodb_table(settings.aws_region, settings.table_name)
    return NarrativeRepository(table, settings.gsi_name)


def get_queue_service(
    settings: Settings = Depends(get_settings),
) -> QueueService:
    """SQS キューサービスを提供する依存関係。

    Args:
        settings: 実行時設定。

    Returns:
        構築済み :class:`QueueService`。
    """

    client = _get_sqs_client(settings.aws_region)
    return QueueService(client, settings.queue_url)


def get_narrative_service(
    repository: NarrativeRepository = Depends(get_repository),
    queue: QueueService = Depends(get_queue_service),
) -> NarrativeService:
    """変換ジョブサービスを提供する依存関係。

    Args:
        repository: DynamoDB リポジトリ。
        queue: SQS キューサービス。

    Returns:
        構築済み :class:`NarrativeService`。
    """

    return NarrativeService(repository, queue)
