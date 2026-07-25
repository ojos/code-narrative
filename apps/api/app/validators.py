"""リクエスト値の業務バリデーションを担うモジュール。

SPEC §4 ① のバリデーション要件（repo_url 形式 / model_id ホワイトリスト）を
実装する。いずれも不正時は 400 Bad Request 相当の :class:`ValidationError` を送出。
"""

from __future__ import annotations

import re
from collections.abc import Collection

# https://github.com/{owner}/{repo} のみを許可する正規表現。
# owner: 先頭英数字 + 英数字/ハイフン（ドットを含まないため `.`/`..` にならない）。
# repo: 英数字・ハイフン・アンダースコア・ドット。ただし `.`/`..` 等のドットのみ名は
#       否定先読み `(?!\.+/?\Z)` で除外する（下流の codeload/commits URL のパス化け防止）。
# 末尾スラッシュは許容するが、それ以降のパス（issues など）は許可しない。
# 照合は :func:`re.fullmatch` で行う。末尾の `$` は Python では文字列末尾の改行の
# 手前にもマッチしバイパスされるため、`fullmatch` + 語中アンカー `\Z` で厳密化する。
_GITHUB_REPO_URL_PATTERN = re.compile(
    r"https://github\.com/[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})/(?!\.+/?\Z)[A-Za-z0-9_.-]{1,100}/?"
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

    if not _GITHUB_REPO_URL_PATTERN.fullmatch(repo_url):
        raise ValidationError(
            "repo_url は https://github.com/{owner}/{repo} 形式のみ許可されます"
        )


def validate_model_id(
    model_id: str, allowed_model_ids: Collection[str]
) -> None:
    """model_id が許可モデルホワイトリストに含まれるか検証する。

    許可集合はモジュール定数ではなく引数で受け取る。呼び出し側（サービス層）が
    :attr:`app.config.Settings.allowed_model_ids`（env ``MODEL_WHITELIST`` 由来）を
    渡すことで、terraform が注入する許可リストと実行時に整合させる。

    Args:
        model_id: 検証対象のモデル ID。
        allowed_model_ids: 許可するモデル ID の集合。

    Raises:
        ValidationError: 許可集合に存在しない場合。
    """

    if model_id not in allowed_model_ids:
        raise ValidationError("model_id が許可モデルホワイトリストに含まれていません")
