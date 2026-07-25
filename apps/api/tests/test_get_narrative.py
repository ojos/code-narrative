"""``GET /api/v1/narratives/{job_id}`` の単体テスト（所有者検証・status 別応答）。"""

from __future__ import annotations

from typing import Any, Callable

from fastapi.testclient import TestClient


def _put_record(table: Any, **overrides: Any) -> dict[str, Any]:
    """テスト用にジョブレコードを直接書き込むヘルパ。

    Args:
        table: DynamoDB Table リソース。
        **overrides: 既定値を上書きする属性。

    Returns:
        書き込んだレコード。
    """

    item = {
        "job_id": "job-1",
        "user_id": "user-1",
        "repo_url": "https://github.com/owner/repo",
        "model_id": "amazon.nova-lite-v1:0",
        "status": "processing",
        "created_at": "2026-07-25T00:00:00Z",
        "updated_at": "2026-07-25T00:00:10Z",
    }
    item.update(overrides)
    table.put_item(Item=item)
    return item


def test_get_returns_record_for_owner(
    client: TestClient,
    aws_backend: dict[str, Any],
    auth_headers: Callable[[str], dict[str, str]],
) -> None:
    """所有者は自分のジョブ詳細を 200 で取得できる。"""

    _put_record(aws_backend["table"], status="processing")

    response = client.get(
        "/api/v1/narratives/job-1", headers=auth_headers("user-1")
    )

    assert response.status_code == 200
    body = response.json()
    assert body["job_id"] == "job-1"
    assert body["status"] == "processing"
    # processing では generated_story / error_message を含まない
    assert "generated_story" not in body
    assert "error_message" not in body


def test_get_completed_includes_generated_story(
    client: TestClient,
    aws_backend: dict[str, Any],
    auth_headers: Callable[[str], dict[str, str]],
) -> None:
    """completed のジョブは generated_story を含む。"""

    _put_record(
        aws_backend["table"],
        status="completed",
        generated_story="むかしむかし…",
    )

    response = client.get(
        "/api/v1/narratives/job-1", headers=auth_headers("user-1")
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "completed"
    assert body["generated_story"] == "むかしむかし…"
    assert "error_message" not in body


def test_get_failed_includes_error_message(
    client: TestClient,
    aws_backend: dict[str, Any],
    auth_headers: Callable[[str], dict[str, str]],
) -> None:
    """failed のジョブは error_message を含み generated_story を含まない。"""

    _put_record(
        aws_backend["table"],
        status="failed",
        error_message="tarball が 200MB を超過しました",
    )

    response = client.get(
        "/api/v1/narratives/job-1", headers=auth_headers("user-1")
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "failed"
    assert body["error_message"] == "tarball が 200MB を超過しました"
    assert "generated_story" not in body


def test_get_returns_404_for_non_owner(
    client: TestClient,
    aws_backend: dict[str, Any],
    auth_headers: Callable[[str], dict[str, str]],
) -> None:
    """所有者でないユーザーには 404 を返す（存在秘匿）。"""

    _put_record(aws_backend["table"], user_id="user-1")

    response = client.get(
        "/api/v1/narratives/job-1", headers=auth_headers("attacker")
    )

    assert response.status_code == 404


def test_get_returns_404_for_missing(
    client: TestClient,
    auth_headers: Callable[[str], dict[str, str]],
) -> None:
    """存在しない job_id には 404 を返す。"""

    response = client.get(
        "/api/v1/narratives/does-not-exist", headers=auth_headers("user-1")
    )

    assert response.status_code == 404
