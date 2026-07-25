"""config モジュールの単体テスト（env 契約: DYNAMODB_TABLE / MODEL_WHITELIST）。

terraform(api モジュール) が注入する環境変数名・値と API 設定が整合することを
検証する。実 AWS へは接続しない。
"""

from __future__ import annotations

import pytest

from app.config import _parse_model_whitelist, get_settings
from app.constants import ALLOWED_MODEL_IDS


def test_parse_model_whitelist_from_env() -> None:
    """カンマ区切り MODEL_WHITELIST を許可集合へ解釈する（空白トリム）。"""

    result = _parse_model_whitelist(
        " jp.anthropic.claude-sonnet-4-5-20250929-v1:0 , amazon.nova-lite-v1:0 "
    )

    assert result == frozenset(
        {
            "jp.anthropic.claude-sonnet-4-5-20250929-v1:0",
            "amazon.nova-lite-v1:0",
        }
    )


def test_parse_model_whitelist_drops_empty_elements() -> None:
    """空要素（連続カンマ・末尾カンマ）は除去される。"""

    result = _parse_model_whitelist("amazon.nova-lite-v1:0,,")

    assert result == frozenset({"amazon.nova-lite-v1:0"})


@pytest.mark.parametrize("value", [None, "", "   ", ",", " , "])
def test_parse_model_whitelist_falls_back_to_default(value: str | None) -> None:
    """未設定/空/空要素のみの場合は既定の許可集合へフォールバックする。"""

    assert _parse_model_whitelist(value) == ALLOWED_MODEL_IDS


def test_get_settings_reads_dynamodb_table_and_whitelist(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """get_settings が DYNAMODB_TABLE と MODEL_WHITELIST を反映する。"""

    monkeypatch.setenv("DYNAMODB_TABLE", "CodeNarratives")
    monkeypatch.setenv("SQS_QUEUE_URL", "https://sqs.local/0/jobs")
    monkeypatch.setenv(
        "MODEL_WHITELIST",
        "jp.anthropic.claude-sonnet-4-5-20250929-v1:0,amazon.nova-lite-v1:0",
    )
    get_settings.cache_clear()
    try:
        settings = get_settings()
    finally:
        get_settings.cache_clear()

    assert settings.table_name == "CodeNarratives"
    assert settings.allowed_model_ids == frozenset(
        {
            "jp.anthropic.claude-sonnet-4-5-20250929-v1:0",
            "amazon.nova-lite-v1:0",
        }
    )


def test_get_settings_requires_dynamodb_table(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """DYNAMODB_TABLE 未設定なら RuntimeError を送出する。"""

    monkeypatch.delenv("DYNAMODB_TABLE", raising=False)
    monkeypatch.setenv("SQS_QUEUE_URL", "https://sqs.local/0/jobs")
    get_settings.cache_clear()
    try:
        with pytest.raises(RuntimeError, match="DYNAMODB_TABLE"):
            get_settings()
    finally:
        get_settings.cache_clear()
