"""ローカル環境に対する統合テスト（issue #74 の受け入れ条件）。

実 AWS リソースへは一切接続しない。DynamoDB / SQS はローカル実装、Bedrock と
GitHub はスタブへ向くため、AWS 資格情報が無くても、外部ネットワークへ到達
できなくても完走する。

検証するのは「各コンポーネント単体」ではなく、**それらを跨いだ経路**である。
単体の振る舞いは各アプリの単体テスト（pytest / go test）が担う。
"""

from __future__ import annotations

import json
import uuid
from typing import Any

import requests
from conftest import (
    DLQ_TIMEOUT_SECONDS,
    JOB_TIMEOUT_SECONDS,
    MISSING_REPO_URL,
    MODEL_ID,
    ApiSession,
    wait_until,
)


def fetch_record(table: Any, job_id: str) -> dict[str, Any] | None:
    """DynamoDB から直接レコードを取得する。

    Args:
        table: DynamoDB Table リソース。
        job_id: 対象ジョブ ID。

    Returns:
        レコード。存在しなければ ``None``。
    """

    return table.get_item(Key={"job_id": job_id}).get("Item")


def wait_for_status(table: Any, job_id: str, status: str) -> dict[str, Any]:
    """レコードが目的のステータスへ遷移するまで待つ。

    Args:
        table: DynamoDB Table リソース。
        job_id: 対象ジョブ ID。
        status: 期待するステータス。

    Returns:
        遷移後のレコード。
    """

    def reached() -> dict[str, Any] | None:
        item = fetch_record(table, job_id)
        if item is None:
            return None
        if item.get("status") == status:
            return item
        assert item.get("status") != "failed" or status == "failed", (
            f"ジョブが failed になりました: {item.get('error_message')}"
        )
        return None

    return wait_until(
        reached,
        timeout=JOB_TIMEOUT_SECONDS,
        description=f"ジョブ {job_id} の status={status} への遷移",
    )


class TestRouting:
    """API Gateway のルーティングと認可の再現を検証する。"""

    def test_health_route_requires_no_authentication(self, api_base_url: str) -> None:
        """``GET /health`` は認証不要で 200 を返す。

        Args:
            api_base_url: API のベース URL。
        """

        response = requests.get(f"{api_base_url}/health", timeout=30)

        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

    def test_request_without_token_is_rejected(self, api_base_url: str) -> None:
        """認証ヘッダの無いリクエストは Authorizer が 401 で弾く。

        Args:
            api_base_url: API のベース URL。
        """

        response = requests.post(
            f"{api_base_url}/api/v1/narratives",
            data=json.dumps({"repo_url": "https://github.com/ojos/stub-repo"}),
            headers={"Content-Type": "application/json"},
            timeout=30,
        )

        assert response.status_code == 401

    def test_undefined_route_returns_404(self, api_base_url: str) -> None:
        """明示ルート以外は 404 になる（``$default`` を持たない構成の再現）。

        Args:
            api_base_url: API のベース URL。
        """

        response = requests.get(f"{api_base_url}/api/v1/unknown", timeout=30)

        assert response.status_code == 404

    def test_connection_is_reusable_after_rejected_request(
        self, api_base_url: str
    ) -> None:
        """ボディ付きの拒否応答のあとも、同じ接続で次のリクエストが通る。

        HTTP/1.1 の keep-alive では、サーバがリクエストボディを読み切らずに
        応答すると、残ったボディが次のリクエストの先頭として解釈され、接続を
        再利用するクライアント（ブラウザや `requests.Session`）が壊れる。

        Args:
            api_base_url: API のベース URL。
        """

        session = requests.Session()

        rejected = session.post(
            f"{api_base_url}/api/v1/narratives",
            data=json.dumps({"repo_url": "https://github.com/ojos/stub-repo"}),
            headers={"Content-Type": "application/json"},
            timeout=30,
        )
        assert rejected.status_code == 401

        # 同一接続の再利用で成功すること（接続が壊れていれば例外か不正な応答になる）。
        followed = session.get(f"{api_base_url}/health", timeout=30)
        assert followed.status_code == 200
        assert followed.json() == {"status": "ok"}

    def test_cors_preflight_is_answered_without_authentication(
        self, api_base_url: str
    ) -> None:
        """OPTIONS は Authorizer を経ずに 204 と CORS ヘッダを返す。

        Args:
            api_base_url: API のベース URL。
        """

        response = requests.options(
            f"{api_base_url}/api/v1/narratives",
            headers={
                "Origin": "http://localhost:8080",
                "Access-Control-Request-Method": "POST",
            },
            timeout=30,
        )

        assert response.status_code == 204
        assert "Access-Control-Allow-Origin" in response.headers
        assert "POST" in response.headers["Access-Control-Allow-Methods"]


class TestValidation:
    """API 層の入力検証を経路越しに検証する。"""

    def test_invalid_repo_url_is_rejected(self, api: ApiSession) -> None:
        """GitHub 以外の URL は 400 で弾かれ、ジョブは作られない。

        Args:
            api: 認証済み API クライアント。
        """

        response = api.create(repo_url="https://example.com/ojos/stub-repo")

        assert response.status_code == 400

    def test_model_outside_whitelist_is_rejected(self, api: ApiSession) -> None:
        """ホワイトリスト外の model_id は 400 で弾かれる。

        Args:
            api: 認証済み API クライアント。
        """

        response = api.create(model_id="anthropic.claude-3-opus-20240229-v1:0")

        assert response.status_code == 400


class TestAsyncPath:
    """同期パスから非同期パスまでを貫いた本流の検証。"""

    def test_job_is_accepted_and_completed_with_story_and_usage(
        self, api: ApiSession, table: Any
    ) -> None:
        """202 受理 → queued → completed へ至り、物語と使用量が永続化される。

        受け入れ条件の中核。API は即座に 202 を返し（LLM の生成時間から独立）、
        ワーカーが SQS 経由で処理して DynamoDB を completed へ更新する。

        Args:
            api: 認証済み API クライアント。
            table: DynamoDB Table リソース。
        """

        created = api.create()
        assert created.status_code == 202

        body = created.json()
        job_id = body["job_id"]
        assert body["status"] == "queued"

        # DynamoDB へ直接問い合わせ、API 応答の整形に依存せず永続化を確認する。
        record = wait_for_status(table, job_id, "completed")

        assert record["user_id"] == api.subject
        assert record["model_id"] == MODEL_ID
        assert record["generated_story"].strip() != ""
        assert record["repo_digest"].strip() != ""
        assert int(record["usage"]["input_tokens"]) > 0
        assert int(record["usage"]["output_tokens"]) > 0

        # API 経由でも同じ結果が読めること（GSI を使わない詳細取得の経路）。
        detail = api.get(job_id)
        assert detail.status_code == 200
        assert detail.json()["generated_story"] == record["generated_story"]

    def test_unfetchable_repository_is_recorded_as_failed(
        self, api: ApiSession, table: Any
    ) -> None:
        """取得できないリポジトリは failed 確定となり、再配信されない。

        Args:
            api: 認証済み API クライアント。
            table: DynamoDB Table リソース。
        """

        created = api.create(repo_url=MISSING_REPO_URL)
        assert created.status_code == 202
        job_id = created.json()["job_id"]

        record = wait_for_status(table, job_id, "failed")

        assert record["error_message"].strip() != ""
        assert "generated_story" not in record


class TestOwnership:
    """GSI 経由の一覧取得が所有者で閉じていることを検証する。"""

    def test_history_lists_only_own_jobs(
        self, api_base_url: str, api: ApiSession
    ) -> None:
        """他ユーザーのジョブは一覧にも詳細にも現れない。

        Args:
            api_base_url: API のベース URL。
            api: 認証済み API クライアント（所有者）。
        """

        created = api.create()
        assert created.status_code == 202
        job_id = created.json()["job_id"]

        owner_listing = api.list(limit=20)
        assert owner_listing.status_code == 200
        assert job_id in [item["job_id"] for item in owner_listing.json()["items"]]

        stranger = ApiSession(api_base_url, f"stranger-{uuid.uuid4()}")
        stranger_listing = stranger.list(limit=20)
        assert stranger_listing.status_code == 200
        assert stranger_listing.json()["items"] == []

        # 存在秘匿のため、他人のジョブ ID を直接指定しても 404 になる。
        assert stranger.get(job_id).status_code == 404


class TestDeadLetterQueue:
    """再配信と DLQ 退避の経路を検証する。"""

    def test_orphan_message_is_redriven_to_dlq(
        self, sqs: Any, queue_url: str, dlq_url: str
    ) -> None:
        """レコードの無いメッセージは削除されず、maxReceiveCount 超過で DLQ へ移る。

        ワーカーは「レコード未挿入」を一時障害として扱い（サイレント削除を避ける）、
        ESM は失敗として報告されたメッセージを削除しない。結果としてキューの
        redrive がメッセージを DLQ へ退避する。

        Args:
            sqs: SQS クライアント。
            queue_url: 変換ジョブキューの URL。
            dlq_url: DLQ の URL。
        """

        orphan_job_id = f"orphan-{uuid.uuid4()}"
        sqs.send_message(
            QueueUrl=queue_url,
            MessageBody=json.dumps(
                {
                    "job_id": orphan_job_id,
                    "repo_url": "https://github.com/ojos/stub-repo",
                    "custom_prompt": "DLQ 経路の検証",
                    "model_id": MODEL_ID,
                }
            ),
        )

        def found_in_dlq() -> dict[str, Any] | None:
            received = sqs.receive_message(
                QueueUrl=dlq_url,
                MaxNumberOfMessages=10,
                WaitTimeSeconds=2,
                VisibilityTimeout=1,
            )
            for message in received.get("Messages", []):
                if json.loads(message["Body"]).get("job_id") == orphan_job_id:
                    return message
            return None

        message = wait_until(
            found_in_dlq,
            timeout=DLQ_TIMEOUT_SECONDS,
            description=f"孤児メッセージ {orphan_job_id} の DLQ 到達",
            interval=0.5,
        )

        assert json.loads(message["Body"])["job_id"] == orphan_job_id
