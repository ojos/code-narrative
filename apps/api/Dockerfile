# AWS Lambda Python コンテナランタイム（SPEC §4 ①: ECR イメージから起動）
FROM public.ecr.aws/lambda/python:3.12

# 依存関係を先にインストールしてレイヤキャッシュを効かせる
COPY requirements.txt ${LAMBDA_TASK_ROOT}/
RUN pip install --no-cache-dir -r ${LAMBDA_TASK_ROOT}/requirements.txt

# アプリケーションコードを配置
COPY app ${LAMBDA_TASK_ROOT}/app

# Mangum ハンドラ（app/main.py の handler）を Lambda ハンドラとして指定
CMD ["app.main.handler"]
