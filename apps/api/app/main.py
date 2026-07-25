"""FastAPI アプリケーションと Lambda ハンドラのエントリポイント。

アプリのファクトリ生成、ルータの登録、構造化ログの初期化、および Mangum に
よる Lambda ハンドラ化を行う（SPEC §4 ①）。
"""

from __future__ import annotations

from fastapi import FastAPI
from mangum import Mangum

from .logging_config import configure_logging
from .routers.narratives import router as narratives_router


def create_app() -> FastAPI:
    """FastAPI アプリケーションを生成して返すファクトリ。

    構造化ログを初期化し、ヘルスチェックと narratives ルータを登録する。

    Returns:
        設定済みの :class:`FastAPI` インスタンス。
    """

    configure_logging()

    app = FastAPI(
        title="code-narrative API",
        description="変換ジョブの受領・記録・エンキュー・取得を提供する REST API",
        version="1.0.0",
    )

    @app.get("/health", tags=["health"], summary="ヘルスチェック")
    def health() -> dict[str, str]:
        """稼働確認用のヘルスチェックエンドポイント。

        Returns:
            ステータスを示す固定レスポンス。
        """

        return {"status": "ok"}

    app.include_router(narratives_router)
    return app


# Lambda / ローカル共通で参照するアプリケーションインスタンス。
app = create_app()

# API Gateway (HTTP API) の Lambda プロキシ統合用ハンドラ。
handler = Mangum(app)
