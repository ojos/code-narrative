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


# SPEC §4 ⑤ で定義された許可モデルホワイトリストの既定値（東京リージョン）。
# 本番では環境変数 ``MODEL_WHITELIST``（terraform 注入）を正とし、この定数は
# 未設定/空のときのフォールバックとして用いる（config.py 参照）。
# ここに存在しない model_id はリクエストを 400 Bad Request で拒否する。
ALLOWED_MODEL_IDS: frozenset[str] = frozenset(
    {
        "jp.anthropic.claude-sonnet-4-5-20250929-v1:0",
        "amazon.nova-lite-v1:0",
    }
)

# GSI の既定名（SPEC §4 ③）。環境変数で上書き可能。
DEFAULT_GSI_NAME = "user_id-created_at-index"
