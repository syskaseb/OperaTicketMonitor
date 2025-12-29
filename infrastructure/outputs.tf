output "lambda_function_name" {
  description = "Name of the Lambda function"
  value       = aws_lambda_function.opera_monitor.function_name
}

output "lambda_function_arn" {
  description = "ARN of the Lambda function"
  value       = aws_lambda_function.opera_monitor.arn
}

output "cloudwatch_log_group" {
  description = "CloudWatch Log Group name"
  value       = aws_cloudwatch_log_group.lambda_logs.name
}

output "schedule_arn" {
  description = "ARN of the EventBridge Scheduler"
  value       = aws_scheduler_schedule.daily.arn
}

output "state_bucket" {
  description = "S3 bucket for persisting monitor state"
  value       = aws_s3_bucket.monitor_state.id
}
