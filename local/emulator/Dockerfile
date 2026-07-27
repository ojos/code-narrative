# syntax=docker/dockerfile:1

# ローカルエミュレータのイメージ定義。
#
# 共通ベース（base ステージ）を 1 つ置き、サービス毎に**自分のモジュールだけ**を
# 載せたイメージを作る。compose 側は build.target でステージを選ぶ。
#
# こうするのは、1 つのイメージを command で使い分けると、どのコンテナが何を
# 持っているのかが読めなくなるため。apigw のコンテナに esm や各スタブのコードが
# 同居していると、責務の境界がイメージからは分からない。
#
# base は全ステージの共通の親なので、レイヤはディスク上で共有される。
# 「サービス毎に分ける」ことで重複して太ることはない。
#
# ビルドコンテキストはリポジトリルート。フロントエンドの静的ファイルを
# bind mount ではなく COPY で焼き込むのは、この devcontainer が
# docker-outside-of-docker 構成で、ホスト側デーモンから見たパスと
# コンテナ内のパスが一致しないため。

# ---- 共通ベース: Python + AWS SDK + 共有ライブラリ ----
FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /opt/service

# 依存解決を先に行いレイヤキャッシュを効かせる。
COPY local/emulator/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# 複数サービスが実際に共有するモジュールのみ。個別サービスのモジュールは置かない。
COPY local/emulator/http_service.py local/emulator/lambda_rie.py ./


# ---- API Gateway (HTTP API) エミュレータ ----
FROM base AS apigw
COPY local/emulator/apigw.py ./
CMD ["python", "apigw.py"]


# ---- SQS イベントソースマッピングのエミュレータ ----
FROM base AS esm
COPY local/emulator/esm.py ./
CMD ["python", "esm.py"]


# ---- Bedrock Converse API スタブ ----
FROM base AS bedrock-stub
COPY local/emulator/bedrock_stub.py ./
CMD ["python", "bedrock_stub.py"]


# ---- GitHub（codeload / REST API）スタブ ----
FROM base AS github-stub
COPY local/emulator/github_stub.py ./
CMD ["python", "github_stub.py"]


# ---- 初期化ジョブ（テーブル作成・キュー確認） ----
FROM base AS init
COPY local/emulator/init_resources.py ./
CMD ["python", "init_resources.py"]


# ---- フロントエンド静的配信（CloudFront + S3 の代替） ----
FROM base AS frontend
COPY local/emulator/frontend_server.py ./
# 配信対象の静的ファイルは、この 1 イメージにだけ入る。
COPY apps/frontend/ /srv/frontend/
CMD ["python", "frontend_server.py"]


# ---- 統合テスト ----
FROM base AS test
COPY local/tests/requirements.txt /opt/tests/requirements.txt
RUN pip install --no-cache-dir -r /opt/tests/requirements.txt
COPY local/tests/ /opt/tests/
# 共有ライブラリ（/opt/service）はテストからも import できるようにしておく。
ENV PYTHONPATH=/opt/service
WORKDIR /opt/tests
CMD ["python", "-m", "pytest", "-v"]
