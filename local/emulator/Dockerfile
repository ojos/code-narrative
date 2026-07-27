# syntax=docker/dockerfile:1

# ローカルエミュレータ共通イメージ。
#
# apigw / esm / bedrock-stub / github-stub / frontend / init / test は、いずれも
# 同じ Python 環境で動く小さなプロセスなので 1 イメージにまとめ、compose 側の
# command で役割を切り替える。
#
# ビルドコンテキストはリポジトリルート。フロントエンドの静的ファイルを
# bind mount ではなく COPY で焼き込むのは、この devcontainer が
# docker-outside-of-docker 構成で、ホスト側デーモンから見たパスと
# コンテナ内のパスが一致しないため。
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /opt/emulator

# 依存解決を先に行いレイヤキャッシュを効かせる。
COPY local/emulator/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY local/emulator/ /opt/emulator/
COPY local/tests/ /opt/tests/

# 静的配信サーバ（frontend_server.py）が読むフロントエンド資材。
COPY apps/frontend/ /srv/frontend/

# エミュレータ本体とテストの双方から共通モジュールを import できるようにする。
ENV PYTHONPATH=/opt/emulator
