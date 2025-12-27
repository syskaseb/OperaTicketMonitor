# Opera Ticket Monitor

Monitors Polish opera houses for ticket availability for **Halka** and **Straszny Dwór** operas, looking for 2+ adjacent seats.

## Features

- Automatic scraping of 9 Polish opera houses every hour
- Email notifications when tickets become available
- Filters to show only future performances (next 6 months)
- Polish date formatting (e.g., "Piątek 7 maja 2026")
- Ready for AWS Lambda deployment
- Remembers what it already notified about (no spam!)

## Monitored Opera Houses

| Opera House | City |
|-------------|------|
| Teatr Wielki - Opera Narodowa | Warsaw |
| Opera Krakowska | Kraków |
| Opera Wrocławska | Wrocław |
| Opera Bałtycka | Gdańsk |
| Opera Śląska | Bytom |
| Opera Nova | Bydgoszcz |
| Teatr Wielki | Łódź |
| Teatr Wielki im. Moniuszki | Poznań |
| Opera i Filharmonia Podlaska | Białystok |

## Quick Start (Local)

### 1. Installation

```bash
# Create venv (Python 3.12+)
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
# or .venv\Scripts\activate  # Windows

# Install dependencies
pip install -r requirements.txt
```

### 2. Email Configuration

To receive notifications, you need:

1. **Gmail account** for sending emails
2. **App Password** (not regular password!) - [how to create](https://support.google.com/accounts/answer/185833)

```bash
# Set environment variables
export SENDER_EMAIL="your-email@gmail.com"
export SENDER_PASSWORD="xxxx-xxxx-xxxx-xxxx"  # App Password!
export RECIPIENT_EMAILS="recipient@gmail.com"
```

### 3. Run

```bash
# Run monitor (continuous)
python monitor.py

# Or single check (for testing)
python -c "from monitor import OperaTicketMonitor; import asyncio; m = OperaTicketMonitor(); asyncio.run(m.run_once())"
```

## AWS Lambda Deployment

### Using Terraform (Recommended)

```bash
cd infrastructure

# Configure variables in terraform.tfvars
# - sender_email
# - sender_password
# - recipient_emails
# - schedule_expression (default: "rate(1 hour)")

terraform init
terraform plan
terraform apply
```

### Manual Test

```bash
# Invoke Lambda manually
aws lambda invoke --function-name opera-ticket-monitor --payload '{}' response.json
cat response.json
```

## Configuration

### Schedule

The monitor runs **every 1 hour** by default. To change, edit `infrastructure/terraform.tfvars`:

```hcl
schedule_expression = "rate(1 hour)"    # Every hour
schedule_expression = "rate(30 minutes)" # Every 30 minutes
schedule_expression = "rate(2 hours)"   # Every 2 hours
```

### Recipients

Edit `infrastructure/terraform.tfvars`:

```hcl
recipient_emails = "email1@gmail.com,email2@gmail.com"
```

### Target Operas

Edit `config.py` to add more operas to search for:

```python
TARGET_OPERAS: list[str] = [
    "Straszny Dwór",
    "Halka",
    # Add more here
]
```

## Project Structure

```
.
├── config.py          # Configuration (opera houses, email, intervals)
├── models.py          # Data models
├── scrapers.py        # Web scrapers for each opera house
├── notifier.py        # Email notification system
├── monitor.py         # Main monitor loop
├── lambda_handler.py  # AWS Lambda handler
├── requirements.txt   # Python dependencies
├── Dockerfile         # For container deployment
└── infrastructure/
    ├── main.tf            # Terraform main config
    ├── lambda.tf          # Lambda resources
    ├── variables.tf       # Input variables
    └── terraform.tfvars   # Variable values
```

## How It Works

1. **Scraping** - Every hour, the program fetches repertoire pages from all opera houses
2. **Parsing** - Searches HTML for mentions of "Halka" or "Straszny Dwór"
3. **Date Filtering** - Only includes performances happening today or in the future
4. **Detection** - Checks if tickets are available or sold out
5. **Notification** - Sends email if new tickets are found
6. **Memory** - Saves what it already notified about (`monitor_state.json`)

## Troubleshooting

### Email not arriving

1. Make sure you're using **App Password**, not regular password
2. Check spam folder
3. Ensure 2FA is enabled on Gmail account

### Scraper not finding performances

Opera websites change frequently. If a scraper stops working:

1. Check logs (CloudWatch for Lambda, or `opera_monitor.log` locally)
2. Open the opera's repertoire page in browser
3. Update selectors in `scrapers.py`

### Lambda timeout

Increase timeout in `infrastructure/lambda.tf` (max 15 minutes for Lambda).

## License

MIT
