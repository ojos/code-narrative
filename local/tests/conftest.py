"""統合テストの共有フィクスチャとヘルパ。

テストは compose ネットワークの内側（`test` サービス）で実行される前提で、
API へは `apigw` エミュレータ越しに、DynamoDB / SQS へは boto3 で直接触る。

`AWS_ENDPOINT_URL_DYNAMODB` / `AWS_ENDPOINT_URL_SQS` は compose が注入するため、
boto3 のクライアント生成側にエンドポイントを書かない（本番と同じ生成コードで動く）。
"""

from __future__ import annotations

import json
import os
import time
import uuid
from collections.abc import Callable
from typing import Any

import boto3
import pytest
import requests

# 変換ジョブが完了するまでの上限秒数。Bedrock はスタブのため実際は数秒で終わる。
# 実 Bedrock へ切り替えると生成に数十秒かかるため、環境変数で引き上げられるようにする。
JOB_TIMEOUT_SECONDS = int(os.environ.get("LOCAL_JOB_TIMEOUT_SECONDS", "120"))
# DLQ へ退避するまでの上限秒数（可視性タイムアウト 5 秒 x maxReceiveCount 5 + 余裕）。
# 可視性タイムアウトを引き上げた場合は、これも併せて引き上げる必要がある。
DLQ_TIMEOUT_SECONDS = int(os.environ.get("LOCAL_DLQ_TIMEOUT_SECONDS", "150"))
# ポーリング間隔。
POLL_INTERVAL_SECONDS = 1.0

# ホワイトリスト内のモデル（terraform の bedrock_model_ids に含まれる）。
MODEL_ID = "amazon.nova-lite-v1:0"
# github-stub が tarball を返すリポジトリ。実 GitHub へは出ない。
STUB_REPO_URL = "https://github.com/ojos/stub-repo"
# github-stub が 404 を返すリポジトリ（恒久エラー経路の検証用）。
MISSING_REPO_URL = "https://github.com/ojos/missing-repo"


@pytest.fixture(scope="session")
def api_base_url() -> str:
    """API Gateway エミュレータのベース URL を返す。

    Returns:
        ``http://apigw:8080`` 形式の URL。
    """

    return os.environ.get("LOCAL_API_BASE_URL", "http://apigw:8080").rstrip("/")


@pytest.fixture(scope="session")
def table() -> Any:
    """ジョブテーブルの DynamoDB Table リソースを返す。

    Returns:
        boto3 の Table リソース。
    """

    resource = boto3.resource("dynamodb", region_name=os.environ["AWS_REGION"])
    return resource.Table(os.environ["DYNAMODB_TABLE"])


@pytest.fixture(scope="session")
def sqs() -> Any:
    """SQS クライアントを返す。

    Returns:
        boto3 の SQS クライアント。
    """

    return boto3.client("sqs", region_name=os.environ["AWS_REGION"])


@pytest.fixture(scope="session")
def queue_url() -> str:
    """変換ジョブキューの URL を返す。

    Returns:
        キュー URL。
    """

    return os.environ["SQS_QUEUE_URL"]


@pytest.fixture(scope="session")
def dlq_url() -> str:
    """DLQ の URL を返す。

    Returns:
        DLQ の URL。
    """

    return os.environ["SQS_DLQ_URL"]


@pytest.fixture
def user() -> str:
    """テストごとに一意なユーザー識別子（``sub``）を返す。

    Returns:
        ``sub`` として使う文字列。
    """

    return f"test-user-{uuid.uuid4()}"


class ApiSession:
    """Bearer トークン付きで API を呼ぶ薄いクライアント。

    Attributes:
        base_url: API のベース URL。
        subject: ``Authorization: Bearer`` に載せる識別子（そのまま ``sub``）。
    """

    def __init__(self, base_url: str, subject: str) -> None:
        """クライアントを初期化する。

        Args:
            base_url: API のベース URL。
            subject: 認証主体（``sub``）。
        """

        self.base_url = base_url
        self.subject = subject
        self._session = requests.Session()

    def create(
        self,
        *,
        repo_url: str = STUB_REPO_URL,
        model_id: str = MODEL_ID,
        custom_prompt: str = "ローカル統合テスト用のプロンプト",
    ) -> requests.Response:
        """変換ジョブを投入する。

        Args:
            repo_url: 対象リポジトリ URL。
            model_id: 使用モデル ID。
            custom_prompt: 世界観・スタイル指定。

        Returns:
            HTTP レスポンス。
        """

        return self._session.post(
            f"{self.base_url}/api/v1/narratives",
            headers=self._headers(),
            data=json.dumps(
                {
                    "repo_url": repo_url,
                    "custom_prompt": custom_prompt,
                    "model_id": model_id,
                }
            ),
            timeout=30,
        )

    def get(self, job_id: str) -> requests.Response:
        """ジョブ詳細を取得する。

        Args:
            job_id: 対象ジョブ ID。

        Returns:
            HTTP レスポンス。
        """

        return self._session.get(
            f"{self.base_url}/api/v1/narratives/{job_id}",
            headers=self._headers(),
            timeout=30,
        )

    def list(self, *, limit: int | None = None) -> requests.Response:
        """自分のジョブ一覧を取得する。

        Args:
            limit: 取得件数の上限。

        Returns:
            HTTP レスポンス。
        """

        params = {} if limit is None else {"limit": str(limit)}
        return self._session.get(
            f"{self.base_url}/api/v1/narratives",
            headers=self._headers(),
            params=params,
            timeout=30,
        )

    def _headers(self) -> dict[str, str]:
        """認証ヘッダを組み立てる。

        Returns:
            リクエストヘッダ。
        """

        return {
            "Authorization": f"Bearer {self.subject}",
            "Content-Type": "application/json",
        }


@pytest.fixture
def api(api_base_url: str, user: str) -> ApiSession:
    """テスト用ユーザーで認証済みの API クライアントを返す。

    Args:
        api_base_url: API のベース URL。
        user: 認証主体。

    Returns:
        構築済み :class:`ApiSession`。
    """

    return ApiSession(api_base_url, user)


def wait_until(
    predicate: Callable[[], Any],
    *,
    timeout: float,
    description: str,
    interval: float = POLL_INTERVAL_SECONDS,
) -> Any:
    """条件が真値を返すまでポーリングし、その値を返す。

    Args:
        predicate: 判定関数。真値を返した時点で成功とする。
        timeout: 上限秒数。
        description: 失敗時のメッセージに使う説明。
        interval: ポーリング間隔（秒）。

    Returns:
        ``predicate`` が返した真値。

    Raises:
        AssertionError: 制限時間内に条件が満たされなかった場合。
    """

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = predicate()
        if result:
            return result
        time.sleep(interval)

    raise AssertionError(f"{description} が {timeout} 秒以内に成立しませんでした")
