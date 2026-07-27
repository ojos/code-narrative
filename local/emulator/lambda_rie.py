"""Lambda Runtime Interface Emulator (RIE) を呼び出すクライアント。

本番の Lambda は API Gateway / SQS イベントソースマッピングから起動される。
ローカルでは、**本番と同一のコンテナイメージ**を RIE 経由で起動し、
`apigw` / `esm` の各エミュレータがイベントを組み立てて RIE を叩く。

これにより「起動経路だけがローカル固有」で、ハンドラ本体（FastAPI + Mangum /
Go の worker.Handle）は本番と同じコードパスを通る。

本モジュールはローカル検証専用であり、本番の Lambda には含まれない。
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

# RIE が公開する Invoke API のパス（関数名は固定で "function"）。
_INVOKE_PATH = "/2015-03-31/functions/function/invocations"

# ハンドラ内で送出された例外を示すレスポンスヘッダ（実 Lambda と同じ名前）。
_FUNCTION_ERROR_HEADER = "X-Amz-Function-Error"


class LambdaInvocationError(RuntimeError):
    """RIE への呼び出し自体が失敗した場合に送出される例外。"""


class LambdaFunctionError(RuntimeError):
    """ハンドラが例外を送出した（関数エラー）場合に送出される例外。

    Attributes:
        error_type: ``X-Amz-Function-Error`` の値（``Unhandled`` 等）。
        payload: RIE が返したエラーペイロード。
    """

    def __init__(self, error_type: str, payload: Any) -> None:
        """例外を初期化する。

        Args:
            error_type: 関数エラーの種別。
            payload: RIE が返したエラーペイロード。
        """

        super().__init__(f"Lambda ハンドラが失敗しました: {error_type}: {payload}")
        self.error_type = error_type
        self.payload = payload


class LambdaRieClient:
    """単一の RIE エンドポイントへイベントを送る同期クライアント。

    Attributes:
        _url: Invoke API の完全な URL。
        _timeout: 1 回の呼び出しの上限秒数。
    """

    def __init__(self, endpoint: str, timeout: float) -> None:
        """クライアントを初期化する。

        Args:
            endpoint: RIE のベース URL（例: ``http://api:8080``）。
            timeout: 呼び出しタイムアウト（秒）。本番の Lambda タイムアウト相当。
        """

        self._url = endpoint.rstrip("/") + _INVOKE_PATH
        self._timeout = timeout

    def invoke(self, event: dict[str, Any]) -> Any:
        """イベントを渡してハンドラを同期実行し、戻り値を返す。

        Args:
            event: Lambda へ渡すイベント（JSON 直列化可能な dict）。

        Returns:
            ハンドラの戻り値を JSON デコードした値。

        Raises:
            LambdaInvocationError: RIE へ到達できない、または応答が JSON でない場合。
            LambdaFunctionError: ハンドラが例外を送出した場合。
        """

        request = urllib.request.Request(
            self._url,
            data=json.dumps(event).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(request, timeout=self._timeout) as response:
                raw = response.read()
                function_error = response.headers.get(_FUNCTION_ERROR_HEADER)
        except urllib.error.URLError as exc:
            raise LambdaInvocationError(f"RIE への呼び出しに失敗しました: {exc}") from exc
        except TimeoutError as exc:
            raise LambdaInvocationError("RIE への呼び出しがタイムアウトしました") from exc

        try:
            payload = json.loads(raw) if raw else None
        except json.JSONDecodeError as exc:
            raise LambdaInvocationError(
                f"RIE の応答を JSON として解釈できません: {raw!r}"
            ) from exc

        if function_error:
            raise LambdaFunctionError(function_error, payload)

        return payload
