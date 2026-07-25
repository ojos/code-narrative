"""アプリケーション全体で共有する定数・列挙型を定義するモジュール。

許可モデルホワイトリスト（SPEC §4 ⑤）とジョブステータス（SPEC §4 ③）を
一箇所に集約し、他モジュールから再利用できるようにする。
"""

from __future__ import annotations

from enum import Enum


class JobStatus(str, Enum):
    """変換ジョブのステータスを表す列挙型。

    DynamoDB レコードの ``status`` 属性および API レスポンスで用いる
    （SPEC §4 ③ の属性構造に対応）。
    """

    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


# SPEC §4 ⑤ で定義された許可モデルホワイトリスト。
# ここに存在しない model_id はリクエストを 400 Bad Request で拒否する。
ALLOWED_MODEL_IDS: frozenset[str] = frozenset(
    {
        "us.anthropic.claude-sonnet-4-5-20250929-v1:0",
        "amazon.nova-lite-v1:0",
        "us.meta.llama3-3-70b-instruct-v1:0",
    }
)

# GSI の既定名（SPEC §4 ③）。環境変数で上書き可能。
DEFAULT_GSI_NAME = "user_id-created_at-index"
