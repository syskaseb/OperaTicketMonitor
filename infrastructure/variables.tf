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

variable "recipient_email" {
  description = "Email address to receive notifications"
  type        = string
  default     = "syskaseb@gmail.com"
}

variable "schedule_expression" {
  description = "CloudWatch Events schedule expression"
  type        = string
  default     = "rate(1 hour)"
}

variable "min_adjacent_seats" {
  description = "Minimum number of adjacent seats to look for"
  type        = number
  default     = 2
}
