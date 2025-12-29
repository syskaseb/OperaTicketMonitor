# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Opera Ticket Monitor - monitors Polish opera houses for availability of tickets to "Halka" and "Straszny Dwór" operas, specifically looking for 2 adjacent seats. Sends email notifications when tickets are found.

## Commands

```bash
# Install dependencies
pip install -r requirements.txt
playwright install chromium

# Run monitor continuously (local)
python monitor.py

# Run single check (for testing locally)
python -c "from monitor import OperaTicketMonitor; import asyncio; m = OperaTicketMonitor(); asyncio.run(m.run_once())"

# AWS Lambda deploy with Terraform
cd infrastructure
terraform init
terraform plan
terraform apply

# Docker build (optional, for manual container deployment)
docker build -t opera-monitor .
```

## Environment Variables

### Local Development
- `SENDER_EMAIL` - Gmail address for sending notifications
- `SENDER_PASSWORD` - Gmail App Password (not regular password)
- `RECIPIENT_EMAILS` - Comma-separated list of recipients (optional for local testing)

### AWS Lambda Deployment
Credentials are stored in AWS Systems Manager Parameter Store (created automatically by Terraform).

## Architecture

The system uses a pipeline architecture:

1. **Scrapers** (`scrapers.py`) - Async scraping of 9 Polish opera repertoire pages using aiohttp. `GenericOperaScraper` handles most sites; `TeatrWielkiWarszawaScraper` is specialized for Warsaw's Opera Narodowa. All scrapers run concurrently via `scrape_all_operas()`.

2. **Seat Checker** (`seat_checker.py`) - Uses Playwright browser automation to check if adjacent seats are available. Navigates to ticket pages, looks for seat maps or availability indicators, detects sold-out shows.

3. **Monitor** (`monitor.py`) - Orchestrates the pipeline: scrapes → checks seats → filters new results → sends notifications. Maintains state in `monitor_state.json` to avoid duplicate notifications.

4. **Notifier** (`notifier.py`) - Sends HTML email notifications via Gmail SMTP. Has separate methods for seat notifications (`send_seat_notification`) vs general performance notifications.

5. **Config** (`config.py`) - Contains `OPERA_HOUSES` list with URLs for each theater, `TARGET_OPERAS` search terms, and `MonitorConfig` settings (15-min interval, retries).

## Key Data Flow

```
OperaHouse configs → scrapers → Performance objects → seat_checker → SeatCheckResult → notifier
                                                                  ↓
                                                          MonitorState (persisted)
```

## Adding a New Opera House

1. Add `OperaHouse` entry to `OPERA_HOUSES` in `config.py` with correct repertoire URL
2. If site has unusual structure, create specialized scraper class in `scrapers.py`
3. If ticket system is different, add handler in `seat_checker.py`

## Polish Opera Sites Quirks

- Many use Brotli compression (requires `Brotli` package)
- Most seat maps are JavaScript-rendered (hence Playwright)
- URLs change frequently - check logs for 404s
- Some sites block automated requests - use realistic User-Agent

## AWS Lambda Deployment Guide

### Prerequisites
- AWS account with credentials configured (`aws configure`)
- Terraform 1.5.0+
- Docker (for building Lambda image)

### Initial Setup (First Time Only)
```bash
# 1. Bootstrap S3 bucket for Terraform state
cd infrastructure
bash bootstrap.sh

# 2. Create terraform.tfvars from example
cp terraform.tfvars.example terraform.tfvars

# 3. Edit terraform.tfvars with your values:
#    - sender_email: Your Gmail address
#    - sender_password: Gmail App Password (see README for instructions)
#    - recipient_emails: Notification recipients
#    - (optional) schedule_expression: Cron/rate expression for schedule
#    - (optional) min_adjacent_seats: Minimum adjacent seats to notify (default: 2)
```

### Deploy
```bash
cd infrastructure
terraform init       # One-time setup
terraform plan       # Review changes
terraform apply      # Deploy to AWS
```

### Configuration Options
- **Schedule**: Default is daily at 14:00 CET (Europe/Warsaw timezone). Set `schedule_expression` in `terraform.tfvars` to customize:
  - `"rate(30 minutes)"` - Every 30 minutes
  - `"cron(0 14 * * ? *)"` - Daily at 14:00 CET

- **Lambda Resources**: 1024 MB memory, 300-second timeout (adjust in `infrastructure/lambda.tf` if needed)

- **Multiple Recipients**: Use comma-separated emails in `terraform.tfvars`:
  ```hcl
  recipient_emails = "user1@gmail.com,user2@gmail.com"
  ```

### Monitor Deployment
```bash
# View Lambda logs in CloudWatch
aws logs tail /aws/lambda/opera-ticket-monitor --follow

# Manually invoke Lambda for testing
aws lambda invoke --function-name opera-ticket-monitor --payload '{}' response.json
cat response.json

# Check Terraform-managed resources
cd infrastructure
terraform state list
terraform state show aws_lambda_function.monitor
```

### Troubleshooting Lambda
- **Timeout errors**: Increase timeout in `infrastructure/lambda.tf`
- **Scraper failures**: Check CloudWatch logs for 404s or site structure changes
- **Email not sending**: Verify credentials in Parameter Store: `aws ssm get-parameter --name /opera-monitor/sender-password`

## GitHub Actions Pipeline

Automated deployment runs on:
- Push to `main` branch
- Pull requests to `main` branch

Pipeline jobs:
1. **test** - Runs pytest against the codebase
2. **deploy** - Runs `terraform plan` and `terraform apply` (only after push to main)

Requires secrets: `SENDER_EMAIL`, `SENDER_PASSWORD`, `RECIPIENT_EMAILS`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`

## AWS Infrastructure

Created by Terraform:
- **ECR Repository**: `opera-ticket-monitor` (stores Lambda container image)
- **Lambda Function**: `opera-ticket-monitor` with Playwright support
- **EventBridge Scheduler**: Triggers Lambda on configured schedule
- **S3 Bucket**: Stores monitor state (`monitor_state.json`)
- **CloudWatch Logs**: 14-day retention for debugging
- **IAM Roles**: Minimal permissions for Lambda execution
- **SSM Parameters**: Secure credential storage
