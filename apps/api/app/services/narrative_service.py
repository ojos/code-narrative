"""変換ジョブのユースケースを統括するサービス層。

バリデーション（validators）・永続化（repository）・エンキュー（queue_service）を
組み合わせ、SPEC §4 ① の処理順序を実装する。HTTP 変換はルータ層が担う。
"""

from __future__ import annotations

import uuid

from ..constants import JobStatus
from ..logging_config import get_logger
from ..models import (
    CreateNarrativeRequest,
    NarrativeDetailResponse,
    NarrativeListResponse,
    build_detail_response,
)
from ..repositories.narrative_repository import NarrativeRepository
from ..utils.pagination import decode_next_token, encode_next_token
from ..utils.time import utcnow_iso
from ..validators import validate_model_id, validate_repo_url
from .queue_service import QueueService

logger = get_logger(__name__)


class OwnershipError(Exception):
    """所有者不一致・レコード不在を表す例外。ルータ層で 404 へ変換する。"""


class NarrativeService:
    """変換ジョブの受領・取得・一覧のユースケースを提供するサービス。

    Attributes:
        _repository: DynamoDB リポジトリ。
        _queue: SQS キューサービス。
        _allowed_model_ids: model_id 検証で許可するモデル ID 集合
            （env ``MODEL_WHITELIST`` 由来）。
    """

    def __init__(
        self,
        repository: NarrativeRepository,
        queue: QueueService,
        allowed_model_ids: frozenset[str],
    ) -> None:
        """サービスを初期化する。

        Args:
            repository: DynamoDB リポジトリ。
            queue: SQS キューサービス。
            allowed_model_ids: 許可するモデル ID 集合（env ``MODEL_WHITELIST`` 由来）。
        """

        self._repository = repository
        self._queue = queue
        self._allowed_model_ids = allowed_model_ids

    def create_narrative(
        self, *, user_id: str, request: CreateNarrativeRequest
    ) -> tuple[str, JobStatus]:
        """変換ジョブを受領し、記録・エンキューする（SPEC §4 ① 手順 1-3）。

        検証成功後、UUID v4 を採番し ``status=queued`` で初期レコードを
        書き込み、SQS へエンキューする。

        Args:
            user_id: JWT の ``sub``。
            request: 検証前のリクエストボディ。

        Returns:
            ``(job_id, JobStatus.QUEUED)`` のタプル。

        Raises:
            ValidationError: repo_url 形式または model_id が不正な場合。
            RepositoryError: 初期レコード書き込みに失敗した場合。
            QueueError: エンキューに失敗した場合。
        """

        validate_repo_url(request.repo_url)
        validate_model_id(request.model_id, self._allowed_model_ids)

        job_id = str(uuid.uuid4())
        created_at = utcnow_iso()

        self._repository.put_initial_record(
            job_id=job_id,
            user_id=user_id,
            repo_url=request.repo_url,
            custom_prompt=request.custom_prompt,
            model_id=request.model_id,
            created_at=created_at,
        )
        self._queue.enqueue_job(
            job_id=job_id,
            repo_url=request.repo_url,
            custom_prompt=request.custom_prompt,
            model_id=request.model_id,
        )

        logger.info(
            "変換ジョブを受領しエンキューしました",
            extra={"job_id": job_id, "user_id": user_id, "status": JobStatus.QUEUED.value},
        )
        return job_id, JobStatus.QUEUED

    def get_narrative(
        self, *, user_id: str, job_id: str
    ) -> NarrativeDetailResponse:
        """所有者検証の上でジョブ詳細を取得する（SPEC §4 ①）。

        レコード不在、または ``user_id`` 不一致はいずれも存在秘匿のため
        :class:`OwnershipError` として扱い、ルータ層で 404 に変換する。

        Args:
            user_id: JWT の ``sub``。
            job_id: 取得対象のジョブ ID。

        Returns:
            構築済みの詳細レスポンスモデル。

        Raises:
            OwnershipError: レコードが存在しない、または所有者が一致しない場合。
            RepositoryError: 取得に失敗した場合。
        """

        item = self._repository.get_by_job_id(job_id)
        if item is None or item.get("user_id") != user_id:
            logger.info(
                "所有者検証に失敗、または対象が存在しません",
                extra={"job_id": job_id, "user_id": user_id},
            )
            raise OwnershipError("指定されたジョブは存在しません")

        return build_detail_response(item)

    def list_narratives(
        self, *, user_id: str, limit: int, next_token: str | None
    ) -> NarrativeListResponse:
        """ユーザー自身のジョブを新しい順に一覧取得する（SPEC §4 ①）。

        Args:
            user_id: JWT の ``sub``。
            limit: 取得件数の上限。
            next_token: 継続取得用トークン（任意）。

        Returns:
            一覧レスポンスモデル。続きがあれば ``next_token`` を含む。

        Raises:
            ValueError: ``next_token`` の形式が不正な場合。
            RepositoryError: クエリに失敗した場合。
        """

        exclusive_start_key = (
            decode_next_token(next_token) if next_token else None
        )

        items, last_key = self._repository.query_by_user(
            user_id=user_id,
            limit=limit,
            exclusive_start_key=exclusive_start_key,
        )

        return NarrativeListResponse(
            items=[build_detail_response(item) for item in items],
            next_token=encode_next_token(last_key) if last_key else None,
        )
