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

# Create deployment package
data "archive_file" "lambda_zip" {
  type        = "zip"
  output_path = "${path.module}/lambda_package.zip"

  source {
    content  = file("${path.module}/../config.py")
    filename = "config.py"
  }
  source {
    content  = file("${path.module}/../models.py")
    filename = "models.py"
  }
  source {
    content  = file("${path.module}/../scrapers.py")
    filename = "scrapers.py"
  }
  source {
    content  = file("${path.module}/../notifier.py")
    filename = "notifier.py"
  }
  source {
    content  = file("${path.module}/../monitor.py")
    filename = "monitor.py"
  }
  source {
    content  = file("${path.module}/../lambda_handler.py")
    filename = "lambda_handler.py"
  }
}

# Lambda Layer for dependencies
resource "aws_lambda_layer_version" "dependencies" {
  filename            = "${path.module}/layer.zip"
  layer_name          = "opera-ticket-monitor-deps"
  compatible_runtimes = ["python3.12"]
  description         = "Dependencies for Opera Ticket Monitor"

  depends_on = [null_resource.create_layer]
}

# Create layer with dependencies (minimal - no Playwright)
resource "null_resource" "create_layer" {
  triggers = {
    requirements_hash = filemd5("${path.module}/../requirements-lambda.txt")
  }

  provisioner "local-exec" {
    command = <<-EOT
      cd ${path.module}
      rm -rf python layer.zip
      mkdir -p python
      pip install -r ../requirements-lambda.txt -t python/ --platform manylinux2014_x86_64 --only-binary=:all: --python-version 3.12 2>/dev/null || pip install -r ../requirements-lambda.txt -t python/
      zip -r layer.zip python
      rm -rf python
    EOT
  }
}

# Lambda function (without Playwright - scraping only)
resource "aws_lambda_function" "opera_monitor" {
  function_name    = "opera-ticket-monitor"
  role             = aws_iam_role.lambda_role.arn
  handler          = "lambda_handler.lambda_handler"
  runtime          = "python3.12"
  filename         = data.archive_file.lambda_zip.output_path
  source_code_hash = data.archive_file.lambda_zip.output_base64sha256
  timeout          = 300
  memory_size      = 512

  layers = [aws_lambda_layer_version.dependencies.arn]

  environment {
    variables = {
      SENDER_EMAIL     = var.sender_email
      SENDER_PASSWORD  = var.sender_password
      RECIPIENT_EMAILS = var.recipient_emails
      MIN_ADJACENT     = var.min_adjacent_seats
      CHECK_SEATS      = "false" # Disable Playwright seat checking in Lambda
    }
  }

  depends_on = [
    aws_cloudwatch_log_group.lambda_logs,
    aws_iam_role_policy.lambda_policy,
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
