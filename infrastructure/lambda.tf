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
    }
  }

  depends_on = [
    aws_cloudwatch_log_group.lambda_logs,
    aws_iam_role_policy.lambda_policy,
    null_resource.docker_build,
  ]
}

# CloudWatch Event Rule (scheduler)
resource "aws_cloudwatch_event_rule" "schedule" {
  name                = "opera-ticket-monitor-schedule"
  description         = "Trigger Opera Ticket Monitor every hour"
  schedule_expression = var.schedule_expression
}

# CloudWatch Event Target
resource "aws_cloudwatch_event_target" "lambda_target" {
  rule      = aws_cloudwatch_event_rule.schedule.name
  target_id = "opera-ticket-monitor"
  arn       = aws_lambda_function.opera_monitor.arn
}

# Lambda permission for CloudWatch Events
resource "aws_lambda_permission" "allow_cloudwatch" {
  statement_id  = "AllowExecutionFromCloudWatch"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.opera_monitor.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.schedule.arn
}
