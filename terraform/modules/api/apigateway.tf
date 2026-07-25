# API Gateway(HTTP API)。Cognito JWT Authorizer + Lambda プロキシ統合(SPEC §2)。
# ルーティングは FastAPI 側が担うため、$default ルートで全リクエストを Lambda に
# プロキシし、Authorizer で Cognito トークンを検証する。

resource "aws_apigatewayv2_api" "this" {
  name          = "${var.function_name}-http"
  protocol_type = "HTTP"

  # SPA は CloudFront の別オリジンから execute-api を呼ぶため CORS が必須。
  # HTTP API の自動プリフライト応答は「どのルートにも一致しない OPTIONS」に対してのみ
  # 働く。$default(catch-all)に JWT を付けると OPTIONS も $default に一致して Authorizer に
  # 回り 401 になり、ブラウザの CORS プリフライトが失敗する。そのため下記のとおり実メソッド
  # のみを明示ルートとして定義し、OPTIONS は無一致にして自動プリフライト(204)へ委ねる。
  cors_configuration {
    allow_origins = var.cors_allow_origins
    allow_headers = ["authorization", "content-type"]
    allow_methods = ["GET", "POST", "OPTIONS"]
    max_age       = 3600
  }
}

resource "aws_apigatewayv2_integration" "lambda" {
  api_id                 = aws_apigatewayv2_api.this.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.this.invoke_arn
  payload_format_version = "2.0"
}

resource "aws_apigatewayv2_authorizer" "jwt" {
  api_id           = aws_apigatewayv2_api.this.id
  name             = "cognito-jwt"
  authorizer_type  = "JWT"
  identity_sources = ["$request.header.Authorization"]

  jwt_configuration {
    audience = [var.cognito_client_id]
    issuer   = var.cognito_issuer
  }
}

# 実メソッド/パスを明示ルートとして定義し、各々に Cognito JWT を適用する。
# OPTIONS ルートは定義しない → プリフライトは cors_configuration による自動応答(204)。
locals {
  jwt_routes = [
    "POST /api/v1/narratives",
    "GET /api/v1/narratives",
    "GET /api/v1/narratives/{job_id}",
  ]
}

resource "aws_apigatewayv2_route" "app" {
  for_each           = toset(local.jwt_routes)
  api_id             = aws_apigatewayv2_api.this.id
  route_key          = each.value
  target             = "integrations/${aws_apigatewayv2_integration.lambda.id}"
  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.jwt.id
}

# 外部死活監視用の認証不要ルート。$default(catch-all)を廃止したため、明示ルートが
# 無いと API Gateway 経由の /health が 404 になる。FastAPI 側の /health は認証を
# 要求しないので、ここでも authorization_type = "NONE" とする。
resource "aws_apigatewayv2_route" "health" {
  api_id             = aws_apigatewayv2_api.this.id
  route_key          = "GET /health"
  target             = "integrations/${aws_apigatewayv2_integration.lambda.id}"
  authorization_type = "NONE"
}

resource "aws_cloudwatch_log_group" "access" {
  name              = "/aws/apigateway/${var.function_name}"
  retention_in_days = var.log_retention_days
}

resource "aws_apigatewayv2_stage" "default" {
  api_id      = aws_apigatewayv2_api.this.id
  name        = "$default"
  auto_deploy = true

  # 構造化(JSON)アクセスログを CloudWatch Logs へ出力する(SPEC §7)。
  access_log_settings {
    destination_arn = aws_cloudwatch_log_group.access.arn
    format = jsonencode({
      requestId      = "$context.requestId"
      ip             = "$context.identity.sourceIp"
      requestTime    = "$context.requestTime"
      httpMethod     = "$context.httpMethod"
      routeKey       = "$context.routeKey"
      status         = "$context.status"
      protocol       = "$context.protocol"
      responseLength = "$context.responseLength"
      integrationErr = "$context.integrationErrorMessage"
    })
  }
}

# API Gateway から Lambda を呼び出す許可。
resource "aws_lambda_permission" "apigw" {
  statement_id  = "AllowApiGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.this.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.this.execution_arn}/*/*"
}
