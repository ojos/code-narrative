# AWS Lambda Python コンテナランタイム（SPEC §4 ①: ECR イメージから起動）
#
# ビルドは uv、実行イメージは素の Lambda ランタイム（uv バイナリを残さない）。
# 依存は uv.lock に固定した本番依存のみを LAMBDA_TASK_ROOT へ展開する。

# --- builder: uv で本番依存を解決・展開 ---
FROM public.ecr.aws/lambda/python:3.12 AS builder

# uv 本体を builder にのみ配置（実行イメージには持ち込まない）
# タグ再発行/差し替えでビルド成果物が変わらないよう digest で固定（可読性のためタグも併記）。
COPY --from=ghcr.io/astral-sh/uv:0.11.32@sha256:df4cae8f3a96d175e2e5f992e597550000edbe78fdc2594d5cd8de1a217f504c /uv /bin/uv

ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1

WORKDIR ${LAMBDA_TASK_ROOT}

# 依存関係を先に解決してレイヤキャッシュを効かせる（アプリコードより前）
COPY pyproject.toml uv.lock ./
# uv.lock を唯一の真実として本番依存（dev 除外）を LAMBDA_TASK_ROOT へ直接インストール
RUN uv export --frozen --no-dev --no-emit-project --no-editable -o requirements.txt \
 && uv pip install --no-cache --system --target "${LAMBDA_TASK_ROOT}" -r requirements.txt \
 && rm requirements.txt pyproject.toml uv.lock

# --- runtime: uv を含まない実行イメージ ---
FROM public.ecr.aws/lambda/python:3.12

# builder で展開した依存を取り込む
COPY --from=builder ${LAMBDA_TASK_ROOT} ${LAMBDA_TASK_ROOT}

# アプリケーションコードを配置
COPY app ${LAMBDA_TASK_ROOT}/app

# Mangum ハンドラ（app/main.py の handler）を Lambda ハンドラとして指定
CMD ["app.main.handler"]
