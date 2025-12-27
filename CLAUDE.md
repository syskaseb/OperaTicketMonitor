# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Opera Ticket Monitor - monitors Polish opera houses for availability of tickets to "Halka" and "Straszny Dwór" operas, specifically looking for 2 adjacent seats. Sends email notifications when tickets are found.

## Commands

```bash
# Install dependencies
pip install -r requirements.txt
playwright install chromium

# Run monitor continuously
python monitor.py

# Run single check (for testing)
python -c "from monitor import OperaTicketMonitor; import asyncio; m = OperaTicketMonitor(); asyncio.run(m.run_once())"

# AWS Lambda deploy
cd aws && sam build && sam deploy --guided

# Docker build
docker build -t opera-monitor .
```

## Environment Variables

- `SENDER_EMAIL` - Gmail address for sending notifications
- `SENDER_PASSWORD` - Gmail App Password (not regular password)

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
