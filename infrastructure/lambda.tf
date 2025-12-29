# IAM Role for Lambda
resource "aws_iam_role" "lambda_role" {
  name = "opera-ticket-monitor-lambda-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
      }
    ]
  })
}

# S3 Bucket for persisting monitor state
resource "aws_s3_bucket" "monitor_state" {
  bucket        = "opera-ticket-monitor-state-${data.aws_caller_identity.current.account_id}"
  force_destroy = true
}

# Block public access to state bucket
resource "aws_s3_bucket_public_access_block" "monitor_state" {
  bucket = aws_s3_bucket.monitor_state.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# IAM Policy for Lambda
resource "aws_iam_role_policy" "lambda_policy" {
  name = "opera-ticket-monitor-lambda-policy"
  role = aws_iam_role.lambda_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = "arn:aws:logs:*:*:*"
      },
      {
        Effect = "Allow"
        Action = [
          "ssm:GetParameter",
          "ssm:GetParameters"
        ]
        Resource = [
          "arn:aws:ssm:${var.aws_region}:${data.aws_caller_identity.current.account_id}:parameter/opera-ticket-monitor/*"
        ]
      },
      {
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:PutObject"
        ]
        Resource = "${aws_s3_bucket.monitor_state.arn}/monitor_state.json"
      }
    ]
  })
}

# CloudWatch Log Group
resource "aws_cloudwatch_log_group" "lambda_logs" {
  name              = "/aws/lambda/opera-ticket-monitor"
  retention_in_days = 14
}

# SSM Parameters for secrets
resource "aws_ssm_parameter" "sender_email" {
  name        = "/opera-ticket-monitor/sender-email"
  description = "Gmail address for sending notifications"
  type        = "SecureString"
  value       = var.sender_email
}

resource "aws_ssm_parameter" "sender_password" {
  name        = "/opera-ticket-monitor/sender-password"
  description = "Gmail App Password"
  type        = "SecureString"
  value       = var.sender_password
}

# ECR Repository for Lambda container image
resource "aws_ecr_repository" "opera_monitor" {
  name                 = "opera-ticket-monitor"
  image_tag_mutability = "MUTABLE"
  force_delete         = true

  image_scanning_configuration {
    scan_on_push = false
  }
}

# Build and push container image
resource "null_resource" "docker_build" {
  triggers = {
    dockerfile_hash = filemd5("${path.module}/../Dockerfile.lambda")
    config_hash     = filemd5("${path.module}/../config.py")
    scrapers_hash   = filemd5("${path.module}/../scrapers.py")
    monitor_hash    = filemd5("${path.module}/../monitor.py")
    notifier_hash   = filemd5("${path.module}/../notifier.py")
    handler_hash    = filemd5("${path.module}/../lambda_handler.py")
  }

  provisioner "local-exec" {
    command = <<-EOT
      cd ${path.module}/..

      # Login to ECR
      aws ecr get-login-password --region ${var.aws_region} | docker login --username AWS --password-stdin ${data.aws_caller_identity.current.account_id}.dkr.ecr.${var.aws_region}.amazonaws.com

      # Build the image
      docker build -f Dockerfile.lambda -t opera-ticket-monitor:latest .

      # Tag for ECR
      docker tag opera-ticket-monitor:latest ${aws_ecr_repository.opera_monitor.repository_url}:latest

      # Push to ECR
      docker push ${aws_ecr_repository.opera_monitor.repository_url}:latest
    EOT
  }

  depends_on = [aws_ecr_repository.opera_monitor]
}

# Lambda function (container image with Playwright support)
resource "aws_lambda_function" "opera_monitor" {
  function_name = "opera-ticket-monitor"
  role          = aws_iam_role.lambda_role.arn
  package_type  = "Image"
  image_uri     = "${aws_ecr_repository.opera_monitor.repository_url}:latest"
  timeout       = 300
  memory_size   = 1024 # Increased for Playwright/Chromium

  environment {
    variables = {
      SENDER_EMAIL     = var.sender_email
      SENDER_PASSWORD  = var.sender_password
      RECIPIENT_EMAILS = var.recipient_emails
      MIN_ADJACENT     = var.min_adjacent_seats
      STATE_BUCKET     = aws_s3_bucket.monitor_state.id
    }
  }

  depends_on = [
    aws_cloudwatch_log_group.lambda_logs,
    aws_iam_role_policy.lambda_policy,
    aws_s3_bucket.monitor_state,
    null_resource.docker_build,
  ]
}

# EventBridge Scheduler (supports timezone)
resource "aws_scheduler_schedule" "daily" {
  name       = "opera-ticket-monitor-daily"
  group_name = "default"

  flexible_time_window {
    mode = "OFF"
  }

  schedule_expression          = "cron(0 14 * * ? *)"
  schedule_expression_timezone = "Europe/Warsaw"

  target {
    arn      = aws_lambda_function.opera_monitor.arn
    role_arn = aws_iam_role.scheduler_role.arn
  }
}

# IAM Role for EventBridge Scheduler
resource "aws_iam_role" "scheduler_role" {
  name = "opera-ticket-monitor-scheduler-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "scheduler.amazonaws.com"
        }
      }
    ]
  })
}

resource "aws_iam_role_policy" "scheduler_policy" {
  name = "opera-ticket-monitor-scheduler-policy"
  role = aws_iam_role.scheduler_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = "lambda:InvokeFunction"
        Resource = aws_lambda_function.opera_monitor.arn
      }
    ]
  })
}

# Invoke Lambda immediately after deployment
resource "null_resource" "invoke_lambda" {
  triggers = {
    lambda_arn   = aws_lambda_function.opera_monitor.arn
    image_digest = null_resource.docker_build.id
  }

  provisioner "local-exec" {
    command = <<-EOT
      echo "Invoking Lambda immediately after deployment..."
      aws lambda invoke \
        --function-name ${aws_lambda_function.opera_monitor.function_name} \
        --invocation-type Event \
        --region ${var.aws_region} \
        /tmp/lambda_response.json
      echo "Lambda invoked successfully"
    EOT
  }

  depends_on = [
    aws_lambda_function.opera_monitor,
    aws_scheduler_schedule.daily,
  ]
}
