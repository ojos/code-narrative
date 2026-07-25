"""テスト共通のフィクスチャ定義。

moto で DynamoDB / SQS を隔離し（実 AWS へは接続しない）、依存性を差し替えた
FastAPI TestClient を提供する。認証トークン生成ヘルパも用意する。
"""

from __future__ import annotations

import base64
import json
import os
from typing import Any, Callable, Iterator

import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws

# 設定モジュール読み込み前に必須環境変数とダミー AWS 資格情報を注入する。
os.environ.setdefault("DYNAMODB_TABLE_NAME", "CodeNarratives")
os.environ.setdefault("SQS_QUEUE_URL", "https://sqs.local/000000000000/jobs")
os.environ.setdefault("AWS_REGION", "us-east-1")
os.environ.setdefault("DYNAMODB_GSI_NAME", "user_id-created_at-index")
os.environ.setdefault("AWS_ACCESS_KEY_ID", "testing")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "testing")
os.environ.setdefault("AWS_SESSION_TOKEN", "testing")

_REGION = "us-east-1"
_TABLE_NAME = "CodeNarratives"
_GSI_NAME = "user_id-created_at-index"


@pytest.fixture
def aws_backend() -> Iterator[dict[str, Any]]:
    """moto で DynamoDB テーブル(+GSI)と SQS キューを構築するフィクスチャ。

    Yields:
        table / sqs クライアント / queue_url を含む辞書。
    """

    with mock_aws():
        dynamodb = boto3.resource("dynamodb", region_name=_REGION)
        table = dynamodb.create_table(
            TableName=_TABLE_NAME,
            KeySchema=[{"AttributeName": "job_id", "KeyType": "HASH"}],
            AttributeDefinitions=[
                {"AttributeName": "job_id", "AttributeType": "S"},
                {"AttributeName": "user_id", "AttributeType": "S"},
                {"AttributeName": "created_at", "AttributeType": "S"},
            ],
            GlobalSecondaryIndexes=[
                {
                    "IndexName": _GSI_NAME,
                    "KeySchema": [
                        {"AttributeName": "user_id", "KeyType": "HASH"},
                        {"AttributeName": "created_at", "KeyType": "RANGE"},
                    ],
                    "Projection": {"ProjectionType": "ALL"},
                }
            ],
            BillingMode="PAY_PER_REQUEST",
        )
        table.wait_until_exists()

        sqs = boto3.client("sqs", region_name=_REGION)
        queue_url = sqs.create_queue(QueueName="jobs")["QueueUrl"]

        yield {"table": table, "sqs": sqs, "queue_url": queue_url}


@pytest.fixture
def client(aws_backend: dict[str, Any]) -> Iterator[TestClient]:
    """依存性を moto バックエンドへ差し替えた TestClient を提供する。

    Args:
        aws_backend: moto で構築した DynamoDB/SQS リソース。

    Yields:
        設定済みの :class:`TestClient`。
    """

    from app.dependencies import get_queue_service, get_repository
    from app.main import create_app
    from app.repositories.narrative_repository import NarrativeRepository
    from app.services.queue_service import QueueService

    app = create_app()
    repository = NarrativeRepository(aws_backend["table"], _GSI_NAME)
    queue = QueueService(aws_backend["sqs"], aws_backend["queue_url"])

    app.dependency_overrides[get_repository] = lambda: repository
    app.dependency_overrides[get_queue_service] = lambda: queue

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()


@pytest.fixture
def make_token() -> Callable[[str], str]:
    """指定 ``sub`` を持つ未署名 JWT 風トークンを生成するヘルパを返す。

    API Gateway が署名検証済みである前提のフォールバック経路
    （Authorization ヘッダの復号）をテストで駆動するために用いる。

    Returns:
        ``sub`` を受け取りトークン文字列を返す関数。
    """

    def _b64url(payload: dict[str, Any]) -> str:
        raw = json.dumps(payload).encode("utf-8")
        return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")

    def _make(sub: str) -> str:
        # alg:none はフォールバックで拒否されるため、署名検証はしないが
        # 実在のアルゴリズム名 + 非空の署名部を持つトークンを生成する。
        header = _b64url({"alg": "RS256", "typ": "JWT"})
        body = _b64url({"sub": sub})
        return f"{header}.{body}.dummysignature"

    return _make


@pytest.fixture
def auth_headers(
    make_token: Callable[[str], str],
) -> Callable[[str], dict[str, str]]:
    """指定 ``sub`` の Authorization ヘッダを生成するヘルパを返す。

    Args:
        make_token: トークン生成ヘルパ。

    Returns:
        ``sub`` を受け取りヘッダ辞書を返す関数。
    """

    def _headers(sub: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {make_token(sub)}"}

    return _headers


@pytest.fixture
def valid_payload() -> dict[str, str]:
    """バリデーションを通過する標準的なリクエストボディを返す。

    Returns:
        有効な repo_url / custom_prompt / model_id を含む辞書。
    """

    return {
        "repo_url": "https://github.com/owner/repo",
        "custom_prompt": "SF風のハードボイルドにして",
        "model_id": "amazon.nova-lite-v1:0",
    }
