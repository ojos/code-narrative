"""Amazon Bedrock Converse API のローカルスタブ。

Bedrock にはローカル代替が存在しないため、`compose.app.yaml` の既定ではこのスタブへ
``AWS_ENDPOINT_URL_BEDROCK_RUNTIME`` を向ける。これにより統合テストは
**オフライン・課金ゼロ・決定的**に完走する。

生成品質を実物で確認したい場合は、`local/README.md` の手順で実 Bedrock
（ap-northeast-1）へ切り替える。ワーカー側のコードは変わらない。

再現するのは ``POST /model/{modelId}/converse`` のみで、応答は Converse API の
出力形（``output.message.content[].text`` / ``usage``）に従う。

本モジュールはローカル検証専用であり、本番には含まれない。
"""

from __future__ import annotations

import json
import re
import urllib.parse
from typing import Any

from http_service import JsonRequestHandler, configure_logging, env_int, serve_forever

logger = configure_logging("bedrock-stub")

LISTEN_PORT = env_int("LOCAL_BEDROCK_STUB_PORT", 8080)

# Converse API のパス。modelId は URL エンコードされて 1 セグメントに収まる。
_CONVERSE_PATH = re.compile(r"^/model/(?P<model_id>[^/]+)/converse$")

# 生成テキストの雛形。model_id を含めることで、テストが「どのモデルで生成されたか」を
# 応答から検証できるようにする。
_STORY_TEMPLATE = (
    "[bedrock-stub] {model_id} が紡いだ物語。\n"
    "リポジトリの構造は静かな都市のようで、コミットの一つひとつが街灯に火を灯していた。\n"
    "ここはローカル環境であり、この文章は決定的に生成された固定文である。"
)


def build_response(model_id: str, request_body: dict[str, Any]) -> dict[str, Any]:
    """Converse API の応答ボディを組み立てる。

    トークン使用量は入力文字数から決定的に導出する。実 Bedrock のトークナイザとは
    一致しないが、「使用量が記録され DynamoDB へ書かれる」ことの検証には十分であり、
    同じ入力からは常に同じ値になる。

    Args:
        model_id: 呼び出し対象のモデル ID。
        request_body: Converse リクエストのボディ。

    Returns:
        Converse API 応答形の dict。
    """

    input_chars = len(json.dumps(request_body, ensure_ascii=False))
    story = _STORY_TEMPLATE.format(model_id=model_id)

    # 4 文字 ≒ 1 トークンの粗い近似。0 にならないよう最低 1 を保証する。
    input_tokens = max(1, input_chars // 4)
    output_tokens = max(1, len(story) // 4)

    return {
        "output": {
            "message": {
                "role": "assistant",
                "content": [{"text": story}],
            }
        },
        "stopReason": "end_turn",
        "usage": {
            "inputTokens": input_tokens,
            "outputTokens": output_tokens,
            "totalTokens": input_tokens + output_tokens,
        },
        "metrics": {"latencyMs": 1},
    }


class BedrockStubHandler(JsonRequestHandler):
    """Converse API を受け付けるスタブハンドラ。"""

    logger = logger

    def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler の規約
        """``POST /model/{modelId}/converse`` を処理する。"""

        matched = _CONVERSE_PATH.match(self.path.split("?", 1)[0])
        if matched is None:
            self.send_json(404, {"message": "Not Found"})
            return

        model_id = urllib.parse.unquote(matched.group("model_id"))

        try:
            raw_body = self.read_body()
        except ValueError as exc:
            self.logger.warning("リクエストボディを読めません: %s", exc)
            self._send_validation_exception("リクエストボディが不正です")
            return

        try:
            request_body = json.loads(raw_body) if raw_body else {}
        except json.JSONDecodeError as exc:
            self.logger.warning("リクエストボディの JSON 解析に失敗: %s", exc)
            self._send_validation_exception("リクエストボディが JSON ではありません")
            return

        self.logger.info("converse: model_id=%s", model_id)
        self.send_json(200, build_response(model_id, request_body))

    def _send_validation_exception(self, message: str) -> None:
        """Bedrock の ``ValidationException`` 形のエラー応答を返す。

        Args:
            message: エラーメッセージ。
        """

        self.send_json(
            400,
            {"message": message},
            {"x-amzn-ErrorType": "ValidationException"},
        )


if __name__ == "__main__":
    serve_forever(BedrockStubHandler, LISTEN_PORT, logger)
