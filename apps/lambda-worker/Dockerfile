# syntax=docker/dockerfile:1

# ---- ビルドステージ ----
# 静的リンクした Lambda ハンドラをビルドする。
FROM golang:1.26 AS build

WORKDIR /src

# 依存解決を先に行いレイヤキャッシュを効かせる。
COPY go.mod go.sum ./
RUN go mod download

COPY . .

# provided.al2023 ランタイム向けに CGO 無効の静的バイナリを生成する。
RUN CGO_ENABLED=0 GOOS=linux go build -tags lambda.norpc -o /main .

# ---- 実行ステージ ----
# AWS 提供の provided ランタイムベースイメージ（コンテナ Lambda）。
FROM public.ecr.aws/lambda/provided:al2023

COPY --from=build /main ${LAMBDA_TASK_ROOT}/main

ENTRYPOINT ["./main"]
