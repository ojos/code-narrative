"""``POST /api/v1/narratives`` のエンドツーエンド単体テスト。

バリデーション（repo_url / model_id）・202 応答・queued レコード書込・
SQS エンキューを moto 隔離下で検証する。
"""

from __future__ import annotations

import json
from typing import Any, Callable

from fastapi.testclient import TestClient


def test_create_returns_202_and_writes_queued_record(
    client: TestClient,
    aws_backend: dict[str, Any],
    auth_headers: Callable[[str], dict[str, str]],
    valid_payload: dict[str, str],
) -> None:
    """エンキュー成功時に 202 と {job_id, status:queued} を返し記録する。"""

    response = client.post(
        "/api/v1/narratives",
        json=valid_payload,
        headers=auth_headers("user-1"),
    )

    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "queued"
    job_id = body["job_id"]
    assert job_id  # 採番されている

    # DynamoDB に queued レコードが書き込まれていること
    item = aws_backend["table"].get_item(Key={"job_id": job_id})["Item"]
    assert item["status"] == "queued"
    assert item["user_id"] == "user-1"
    assert item["repo_url"] == valid_payload["repo_url"]
    assert item["model_id"] == valid_payload["model_id"]

    # SQS にメッセージが投入され、job_id を含むこと
    messages = aws_backend["sqs"].receive_message(
        QueueUrl=aws_backend["queue_url"], MaxNumberOfMessages=10
    ).get("Messages", [])
    assert len(messages) == 1
    enqueued = json.loads(messages[0]["Body"])
    assert enqueued["job_id"] == job_id
    assert enqueued["model_id"] == valid_payload["model_id"]


def test_create_rejects_invalid_repo_url_with_400(
    client: TestClient,
    auth_headers: Callable[[str], dict[str, str]],
    valid_payload: dict[str, str],
) -> None:
    """repo_url 形式が不正な場合は 400 を返す。"""

    payload = dict(valid_payload)
    payload["repo_url"] = "https://github.com/owner/repo/tree/main"

    response = client.post(
        "/api/v1/narratives", json=payload, headers=auth_headers("user-1")
    )

    assert response.status_code == 400


def test_create_rejects_unknown_model_id_with_400(
    client: TestClient,
    auth_headers: Callable[[str], dict[str, str]],
    valid_payload: dict[str, str],
) -> None:
    """model_id がホワイトリスト外の場合は 400 を返す。"""

    payload = dict(valid_payload)
    payload["model_id"] = "anthropic.claude-not-allowed"

    response = client.post(
        "/api/v1/narratives", json=payload, headers=auth_headers("user-1")
    )

    assert response.status_code == 400


def test_create_accepts_jp_whitelisted_model_id(
    client: TestClient,
    auth_headers: Callable[[str], dict[str, str]],
    valid_payload: dict[str, str],
) -> None:
    """settings.allowed_model_ids（東京 jp. モデル）は 202 で受理される。"""

    payload = dict(valid_payload)
    payload["model_id"] = "jp.anthropic.claude-sonnet-4-5-20250929-v1:0"

    response = client.post(
        "/api/v1/narratives", json=payload, headers=auth_headers("user-1")
    )

    assert response.status_code == 202


def test_create_rejects_legacy_us_model_id_with_400(
    client: TestClient,
    auth_headers: Callable[[str], dict[str, str]],
    valid_payload: dict[str, str],
) -> None:
    """旧 us. リージョンのモデル ID は許可集合外のため 400 を返す。"""

    payload = dict(valid_payload)
    payload["model_id"] = "us.anthropic.claude-sonnet-4-5-20250929-v1:0"

    response = client.post(
        "/api/v1/narratives", json=payload, headers=auth_headers("user-1")
    )

    assert response.status_code == 400


def test_create_requires_authentication(
    client: TestClient,
    valid_payload: dict[str, str],
) -> None:
    """認証ヘッダが無い場合は 401 を返す。"""

    response = client.post("/api/v1/narratives", json=valid_payload)

    assert response.status_code == 401


def test_create_rejects_oversized_custom_prompt_with_422(
    client: TestClient,
    auth_headers: Callable[[str], dict[str, str]],
    valid_payload: dict[str, str],
) -> None:
    """custom_prompt が上限（2000 文字）を超える場合は 422 を返す。"""

    payload = dict(valid_payload)
    payload["custom_prompt"] = "あ" * 2001

    response = client.post(
        "/api/v1/narratives", json=payload, headers=auth_headers("user-1")
    )

    assert response.status_code == 422


def test_create_accepts_custom_prompt_at_limit_and_empty(
    client: TestClient,
    auth_headers: Callable[[str], dict[str, str]],
    valid_payload: dict[str, str],
) -> None:
    """custom_prompt が上限ちょうど、または未指定なら従来どおり 202 で受理する。"""

    at_limit = dict(valid_payload)
    at_limit["custom_prompt"] = "あ" * 2000
    response_at_limit = client.post(
        "/api/v1/narratives", json=at_limit, headers=auth_headers("user-1")
    )
    assert response_at_limit.status_code == 202

    without_prompt = {
        "repo_url": valid_payload["repo_url"],
        "model_id": valid_payload["model_id"],
    }
    response_without = client.post(
        "/api/v1/narratives", json=without_prompt, headers=auth_headers("user-1")
    )
    assert response_without.status_code == 202
