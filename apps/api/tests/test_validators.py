"""validators モジュールの単体テスト（repo_url 形式 / model_id ホワイトリスト）。"""

from __future__ import annotations

import pytest

from app.validators import ValidationError, validate_model_id, validate_repo_url


@pytest.mark.parametrize(
    "url",
    [
        "https://github.com/owner/repo",
        "https://github.com/owner/repo/",
        "https://github.com/my-org/my_repo.name",
    ],
)
def test_validate_repo_url_accepts_valid(url: str) -> None:
    """正しい GitHub リポジトリ URL は例外を送出しない。"""

    validate_repo_url(url)  # 例外が出ないことを確認


@pytest.mark.parametrize(
    "url",
    [
        "http://github.com/owner/repo",  # https でない
        "https://gitlab.com/owner/repo",  # ホスト違い
        "https://github.com/owner",  # repo 欠落
        "https://github.com/owner/repo/issues",  # 余分なパス
        "ftp://github.com/owner/repo",
        "https://github.com//repo",  # owner 欠落
        "not-a-url",
        "https://github.com/owner/repo\n",  # 末尾改行バイパス
        "https://github.com/owner/repo\n.evil",  # 改行後に別内容
        "https://github.com/owner/..",  # 親ディレクトリ参照 repo 名
        "https://github.com/owner/.",  # カレントディレクトリ参照 repo 名
        "https://github.com/owner/...",  # ドットのみ repo 名
        "https://github.com/owner/../",  # 末尾スラッシュ付きでも拒否
    ],
)
def test_validate_repo_url_rejects_invalid(url: str) -> None:
    """不正な repo_url は ValidationError を送出する。"""

    with pytest.raises(ValidationError):
        validate_repo_url(url)


# terraform の MODEL_WHITELIST（東京 2 モデル）相当の許可集合。
_ALLOWED = frozenset(
    {
        "jp.anthropic.claude-sonnet-4-5-20250929-v1:0",
        "amazon.nova-lite-v1:0",
    }
)


@pytest.mark.parametrize(
    "model_id",
    [
        "jp.anthropic.claude-sonnet-4-5-20250929-v1:0",
        "amazon.nova-lite-v1:0",
    ],
)
def test_validate_model_id_accepts_whitelisted(model_id: str) -> None:
    """許可集合内の model_id は例外を送出しない。"""

    validate_model_id(model_id, _ALLOWED)  # 例外が出ないことを確認


@pytest.mark.parametrize(
    "model_id",
    [
        "gpt-4o",
        "us.anthropic.claude-sonnet-4-5-20250929-v1:0",  # 旧 us. リージョン
        "us.meta.llama3-3-70b-instruct-v1:0",  # 旧 Llama
    ],
)
def test_validate_model_id_rejects_unknown(model_id: str) -> None:
    """許可集合外の model_id は ValidationError を送出する。"""

    with pytest.raises(ValidationError):
        validate_model_id(model_id, _ALLOWED)
