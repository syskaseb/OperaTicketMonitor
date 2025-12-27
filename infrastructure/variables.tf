variable "aws_region" {
  description = "AWS region"
  type        = string
  default     = "eu-central-1"
}

variable "environment" {
  description = "Environment name"
  type        = string
  default     = "prod"
}

variable "sender_email" {
  description = "Gmail address for sending notifications"
  type        = string
  sensitive   = true
}

variable "sender_password" {
  description = "Gmail App Password"
  type        = string
  sensitive   = true
}

variable "recipient_emails" {
  description = "Email addresses to receive notifications (comma-separated)"
  type        = string
  # No default - must be provided via TF_VAR_recipient_emails or tfvars
}

variable "schedule_expression" {
  description = "CloudWatch Events schedule expression"
  type        = string
  default     = "cron(0 13 * * ? *)" # Daily at 14:00 CET (13:00 UTC)
}

variable "min_adjacent_seats" {
  description = "Minimum number of adjacent seats to look for"
  type        = number
  default     = 2
}
