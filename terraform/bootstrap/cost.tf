# --- コスト統制: AWS Budgets ---
# 注意: limit_unit はアカウントの請求通貨に一致させること。
# USD 請求アカウントの場合は budget_currency を "USD" にし、金額も見直す。

resource "aws_budgets_budget" "monthly" {
  name         = "code-narrative-monthly"
  budget_type  = "COST"
  limit_amount = var.budget_limit_amount
  limit_unit   = var.budget_currency
  time_unit    = "MONTHLY"

  dynamic "notification" {
    for_each = [50, 80, 100]
    content {
      comparison_operator        = "GREATER_THAN"
      threshold                  = notification.value
      threshold_type             = "PERCENTAGE"
      notification_type          = "ACTUAL"
      subscriber_email_addresses = var.notification_emails
    }
  }

  # 予測値が 100% を超える見込みでも通知
  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 100
    threshold_type             = "PERCENTAGE"
    notification_type          = "FORECASTED"
    subscriber_email_addresses = var.notification_emails
  }
}

# --- コスト統制: Cost Anomaly Detection ---

resource "aws_ce_anomaly_monitor" "service" {
  name              = "code-narrative-service-monitor"
  monitor_type      = "DIMENSIONAL"
  monitor_dimension = "SERVICE"
}

resource "aws_ce_anomaly_subscription" "default" {
  name      = "code-narrative-anomaly-subscription"
  frequency = "DAILY"

  monitor_arn_list = [aws_ce_anomaly_monitor.service.arn]

  subscriber {
    type    = "EMAIL"
    address = var.notification_emails[0]
  }

  # 一定額以上の異常のみ通知(通知過多を防ぐ)
  threshold_expression {
    dimension {
      key           = "ANOMALY_TOTAL_IMPACT_ABSOLUTE"
      match_options = ["GREATER_THAN_OR_EQUAL"]
      values        = ["10"]
    }
  }
}
