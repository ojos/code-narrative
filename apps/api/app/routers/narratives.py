"""``/api/v1/narratives`` 配下のエンドポイントを定義するルータ。

サービス層の例外を HTTP ステータスへ変換し、SPEC §4 ① のインターフェースを
公開する。ビジネスロジックは :class:`NarrativeService` に委譲する。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status

from ..auth import get_current_user_id
from ..dependencies import get_narrative_service
from ..logging_config import get_logger
from ..models import (
    CreateNarrativeRequest,
    CreateNarrativeResponse,
    NarrativeDetailResponse,
    NarrativeListResponse,
)
from ..repositories.narrative_repository import RepositoryError
from ..services.narrative_service import NarrativeService, OwnershipError
from ..services.queue_service import QueueError
from ..validators import ValidationError

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1/narratives", tags=["narratives"])


@router.post(
    "",
    response_model=CreateNarrativeResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="変換ジョブの投入",
)
def create_narrative(
    request: CreateNarrativeRequest,
    user_id: str = Depends(get_current_user_id),
    service: NarrativeService = Depends(get_narrative_service),
) -> CreateNarrativeResponse:
    """変換ジョブを受領し、記録・エンキューして 202 を返す（SPEC §4 ①）。

    Args:
        request: リクエストボディ。
        user_id: 認証ユーザーの ``sub``。
        service: 変換ジョブサービス。

    Returns:
        採番された ``job_id`` と ``status=queued`` を含むレスポンス。

    Raises:
        HTTPException: バリデーション失敗は 400、永続化/エンキュー失敗は 502。
    """

    try:
        job_id, job_status = service.create_narrative(
            user_id=user_id, request=request
        )
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=exc.message
        ) from exc
    except (RepositoryError, QueueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="ジョブの受領処理に失敗しました",
        ) from exc

    return CreateNarrativeResponse(job_id=job_id, status=job_status)


@router.get(
    "",
    response_model=NarrativeListResponse,
    response_model_exclude_none=True,
    summary="自分のジョブ一覧取得",
)
def list_narratives(
    user_id: str = Depends(get_current_user_id),
    service: NarrativeService = Depends(get_narrative_service),
    limit: int = Query(default=20, ge=1, le=100),
    next_token: str | None = Query(default=None),
) -> NarrativeListResponse:
    """認証ユーザー自身のジョブを新しい順に一覧取得する（SPEC §4 ①）。

    Args:
        user_id: 認証ユーザーの ``sub``。
        service: 変換ジョブサービス。
        limit: 取得件数の上限（既定 20）。
        next_token: 継続取得用トークン（任意）。

    Returns:
        一覧レスポンス。続きがあれば ``next_token`` を含む。

    Raises:
        HTTPException: ``next_token`` 不正は 400、取得失敗は 502。
    """

    try:
        return service.list_narratives(
            user_id=user_id, limit=limit, next_token=next_token
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc
    except RepositoryError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="一覧取得に失敗しました",
        ) from exc


@router.get(
    "/{job_id}",
    response_model=NarrativeDetailResponse,
    response_model_exclude_none=True,
    summary="結果取得",
)
def get_narrative(
    job_id: str,
    user_id: str = Depends(get_current_user_id),
    service: NarrativeService = Depends(get_narrative_service),
) -> NarrativeDetailResponse:
    """所有者検証の上でジョブ詳細を取得する（SPEC §4 ①）。

    Args:
        job_id: 取得対象のジョブ ID。
        user_id: 認証ユーザーの ``sub``。
        service: 変換ジョブサービス。

    Returns:
        ジョブ詳細レスポンス（status に応じた属性を含む）。

    Raises:
        HTTPException: 所有者不一致・不在は 404、取得失敗は 502。
    """

    try:
        return service.get_narrative(user_id=user_id, job_id=job_id)
    except OwnershipError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=exc.args[0]
        ) from exc
    except RepositoryError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="結果取得に失敗しました",
        ) from exc
