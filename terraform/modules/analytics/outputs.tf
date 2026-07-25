output "stats_function_name" {
  description = "集計 Lambda 関数名(CI のコード更新対象)"
  value       = aws_lambda_function.stats.function_name
}

output "stats_function_arn" {
  description = "集計 Lambda 関数 ARN"
  value       = aws_lambda_function.stats.arn
}

output "state_machine_arn" {
  description = "集計バッチのステートマシン ARN"
  value       = aws_sfn_state_machine.aggregate.arn
}

output "schedule_name" {
  description = "日次スケジュール名"
  value       = aws_scheduler_schedule.daily.name
}
