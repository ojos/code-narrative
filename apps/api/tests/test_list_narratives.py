"""``GET /api/v1/narratives`` の単体テスト（新しい順・limit・next_token）。"""

from __future__ import annotations

from typing import Any, Callable

from fastapi.testclient import TestClient


def _seed_records(table: Any, user_id: str, count: int) -> None:
    """created_at が昇順に異なる複数レコードを投入するヘルパ。

    Args:
        table: DynamoDB Table リソース。
        user_id: 所有者。
        count: 投入件数。
    """

    for i in range(count):
        table.put_item(
            Item={
                "job_id": f"{user_id}-job-{i}",
                "user_id": user_id,
                "repo_url": "https://github.com/owner/repo",
                "model_id": "amazon.nova-lite-v1:0",
                "status": "queued",
                "created_at": f"2026-07-25T00:00:0{i}Z",
                "updated_at": f"2026-07-25T00:00:0{i}Z",
            }
        )


def test_list_returns_newest_first_and_only_own(
    client: TestClient,
    aws_backend: dict[str, Any],
    auth_headers: Callable[[str], dict[str, str]],
) -> None:
    """自分のジョブのみを新しい順で返す。"""

    _seed_records(aws_backend["table"], "user-1", 3)
    _seed_records(aws_backend["table"], "other", 2)

    response = client.get(
        "/api/v1/narratives", headers=auth_headers("user-1")
    )

    assert response.status_code == 200
    body = response.json()
    ids = [item["job_id"] for item in body["items"]]
    # 新しい順（created_at 降順）: job-2, job-1, job-0
    assert ids == ["user-1-job-2", "user-1-job-1", "user-1-job-0"]
    assert body.get("next_token") is None


def test_list_paginates_with_limit_and_next_token(
    client: TestClient,
    aws_backend: dict[str, Any],
    auth_headers: Callable[[str], dict[str, str]],
) -> None:
    """limit と next_token で全件をページ分割して取得できる。"""

    _seed_records(aws_backend["table"], "user-1", 3)

    first = client.get(
        "/api/v1/narratives",
        params={"limit": 2},
        headers=auth_headers("user-1"),
    ).json()
    assert len(first["items"]) == 2
    assert first["next_token"]

    second = client.get(
        "/api/v1/narratives",
        params={"limit": 2, "next_token": first["next_token"]},
        headers=auth_headers("user-1"),
    ).json()
    assert len(second["items"]) == 1

    all_ids = [i["job_id"] for i in first["items"]] + [
        i["job_id"] for i in second["items"]
    ]
    assert all_ids == [
        "user-1-job-2",
        "user-1-job-1",
        "user-1-job-0",
    ]


def test_list_rejects_invalid_next_token_with_400(
    client: TestClient,
    auth_headers: Callable[[str], dict[str, str]],
) -> None:
    """不正な next_token は 400 を返す。"""

    response = client.get(
        "/api/v1/narratives",
        params={"next_token": "!!!not-base64!!!"},
        headers=auth_headers("user-1"),
    )

    assert response.status_code == 400


def test_list_requires_authentication(client: TestClient) -> None:
    """認証ヘッダが無い場合は 401 を返す。"""

    response = client.get("/api/v1/narratives")

    assert response.status_code == 401
