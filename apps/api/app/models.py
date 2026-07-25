"""API のリクエスト/レスポンスを表す Pydantic モデルを定義するモジュール。

SPEC §4 ① のリクエストボディ・各レスポンス、および DynamoDB レコードから
レスポンスを構築するシリアライザを提供する。
"""

from __future__ import annotations

from typing import Any, Mapping

from pydantic import BaseModel, Field

from .constants import JobStatus


class CreateNarrativeRequest(BaseModel):
    """``POST /api/v1/narratives`` のリクエストボディ。

    Attributes:
        repo_url: 変換対象の GitHub リポジトリ URL。
        custom_prompt: 世界観・スタイル指定（任意）。
        model_id: 使用する Bedrock モデル ID（ホワイトリスト照合対象）。
    """

    repo_url: str = Field(..., description="https://github.com/{owner}/{repo} 形式")
    custom_prompt: str = Field(default="", description="世界観・スタイル指定")
    model_id: str = Field(..., description="許可モデルホワイトリスト内の ID")


class CreateNarrativeResponse(BaseModel):
    """``POST /api/v1/narratives`` の 202 レスポンス。

    Attributes:
        job_id: 採番された UUID v4。
        status: 常に ``queued``。
    """

    job_id: str
    status: JobStatus


class NarrativeDetailResponse(BaseModel):
    """ジョブ詳細レスポンス（``GET /api/v1/narratives/{job_id}``）。

    status に応じて可視となる属性が変化する。未設定属性は
    ``response_model_exclude_none`` により応答から除外する（SPEC §4 ①）。

    Attributes:
        job_id: ジョブ ID。
        repo_url: 対象リポジトリ URL。
        status: 現在のステータス。
        model_id: 使用モデル（任意）。
        generated_story: 生成された小説（completed 時のみ）。
        error_message: 失敗理由（failed 時のみ）。
        created_at: 作成時刻（ISO8601）。
        updated_at: 更新時刻（ISO8601、任意）。
    """

    job_id: str
    repo_url: str
    status: JobStatus
    model_id: str | None = None
    generated_story: str | None = None
    error_message: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


class NarrativeListResponse(BaseModel):
    """ジョブ一覧レスポンス（``GET /api/v1/narratives``）。

    Attributes:
        items: 新しい順に並んだジョブ一覧。
        next_token: 次ページ取得用トークン（続きが無ければ ``None``）。
    """

    items: list[NarrativeDetailResponse]
    next_token: str | None = None


def build_detail_response(item: Mapping[str, Any]) -> NarrativeDetailResponse:
    """DynamoDB レコードから詳細レスポンスモデルを構築する。

    status に応じて completed 時のみ ``generated_story``、failed 時のみ
    ``error_message`` を含める（SPEC §4 ① のレスポンス仕様）。

    Args:
        item: DynamoDB から取得したジョブレコード。

    Returns:
        構築された :class:`NarrativeDetailResponse`。
    """

    status = item.get("status")
    generated_story = (
        item.get("generated_story")
        if status == JobStatus.COMPLETED.value
        else None
    )
    error_message = (
        item.get("error_message") if status == JobStatus.FAILED.value else None
    )

    return NarrativeDetailResponse(
        job_id=item["job_id"],
        repo_url=item["repo_url"],
        status=item["status"],
        model_id=item.get("model_id"),
        generated_story=generated_story,
        error_message=error_message,
        created_at=item.get("created_at"),
        updated_at=item.get("updated_at"),
    )
