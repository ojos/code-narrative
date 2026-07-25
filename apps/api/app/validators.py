"""リクエスト値の業務バリデーションを担うモジュール。

SPEC §4 ① のバリデーション要件（repo_url 形式 / model_id ホワイトリスト）を
実装する。いずれも不正時は 400 Bad Request 相当の :class:`ValidationError` を送出。
"""

from __future__ import annotations

import re

from .constants import ALLOWED_MODEL_IDS

# https://github.com/{owner}/{repo} のみを許可する正規表現。
# owner: 英数字とハイフン、repo: 英数字・ハイフン・アンダースコア・ドット。
# 末尾スラッシュは許容するが、それ以降のパス（issues など）は許可しない。
_GITHUB_REPO_URL_PATTERN = re.compile(
    r"^https://github\.com/[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})/[A-Za-z0-9_.-]{1,100}/?$"
)


class ValidationError(Exception):
    """業務バリデーション失敗を表す例外。

    ルータ層でこの例外を捕捉し、HTTP 400 応答へ変換する。

    Attributes:
        message: 失敗理由の説明。
    """

    def __init__(self, message: str) -> None:
        """例外を初期化する。

        Args:
            message: 失敗理由の説明。
        """

        super().__init__(message)
        self.message = message


def validate_repo_url(repo_url: str) -> None:
    """repo_url が ``https://github.com/{owner}/{repo}`` 形式か検証する。

    Args:
        repo_url: 検証対象の URL 文字列。

    Raises:
        ValidationError: 形式に一致しない場合。
    """

    if not _GITHUB_REPO_URL_PATTERN.match(repo_url):
        raise ValidationError(
            "repo_url は https://github.com/{owner}/{repo} 形式のみ許可されます"
        )


def validate_model_id(model_id: str) -> None:
    """model_id が許可モデルホワイトリストに含まれるか検証する。

    Args:
        model_id: 検証対象のモデル ID。

    Raises:
        ValidationError: ホワイトリストに存在しない場合。
    """

    if model_id not in ALLOWED_MODEL_IDS:
        raise ValidationError("model_id が許可モデルホワイトリストに含まれていません")
