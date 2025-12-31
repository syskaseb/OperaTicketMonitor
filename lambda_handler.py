"""
AWS Lambda handler for Opera Ticket Monitor

This allows running the monitor as a serverless function triggered by CloudWatch Events.
Much cheaper than running an EC2 instance 24/7.
"""
import os

# Set Playwright browsers path BEFORE importing playwright
# This must be done early, before any playwright imports
os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", "/opt/playwright-browsers")

import asyncio
import json
import logging
from datetime import datetime

# Set up logging for Lambda
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Import monitor components
from config import get_config
from models import MonitorState
from notifier import EmailNotifier
from scrapers import scrape_all_operas


def lambda_handler(event, context):
    """
    AWS Lambda entry point.

    Triggered by CloudWatch Events (scheduled rule) every 15 minutes.
    """
    logger.info(f"Lambda invoked at {datetime.now().isoformat()}")
    logger.info(f"Event: {json.dumps(event)}")

    try:
        # Run the async check
        result = asyncio.get_event_loop().run_until_complete(check_tickets())

        return {
            "statusCode": 200,
            "body": json.dumps({
                "message": "Check completed successfully",
                "performances_found": result["total"],
                "new_notifications": result["new"],
                "timestamp": datetime.now().isoformat(),
            }),
        }
    except Exception as e:
        logger.error(f"Lambda error: {e}", exc_info=True)

        return {
            "statusCode": 500,
            "body": json.dumps({
                "message": "Error during check",
                "error": str(e),
            }),
        }


async def check_tickets() -> dict:
    """Perform ticket check"""
    config = get_config()

    # In Lambda, we use /tmp for writable storage
    state_file = "/tmp/monitor_state.json"

    # Try to load state from environment or S3 (for persistence between invocations)
    state = await load_state_from_s3() or MonitorState.load(state_file)

    notifier = EmailNotifier(config.email)

    # Scrape all opera houses
    results = await scrape_all_operas(config.opera_houses, config.monitor)

    all_performances = []
    new_performances = []

    for result in results:
        if result.success:
            logger.info(
                f"✓ {result.opera_house}: {len(result.performances)} performances"
            )

            for perf in result.performances:
                all_performances.append(perf)

                if state.should_notify(perf):
                    new_performances.append(perf)
                    logger.info(f"  NEW: {perf.opera_name} @ {perf.opera_house}")
        else:
            logger.warning(f"✗ {result.opera_house}: {result.error_message}")

    # Send notifications
    if new_performances:
        success = notifier.send_notification(new_performances, is_new=True)

        if success:
            for perf in new_performances:
                state.mark_notified(perf)

            # Save state locally and to S3
            state.save(state_file)
            await save_state_to_s3(state)

    return {
        "total": len(all_performances),
        "new": len(new_performances),
    }


async def load_state_from_s3():
    """
    Load state from S3 for persistence between Lambda invocations.
    Returns None if S3 is not configured or state doesn't exist.
    """
    bucket = os.getenv("STATE_BUCKET")
    if not bucket:
        return None

    try:
        import boto3

        s3 = boto3.client("s3")
        response = s3.get_object(Bucket=bucket, Key="monitor_state.json")
        data = json.loads(response["Body"].read().decode("utf-8"))

        return MonitorState(
            notified_performances=set(data.get("notified_performances", [])),
            last_check_times={
                k: datetime.fromisoformat(v)
                for k, v in data.get("last_check_times", {}).items()
            },
        )
    except Exception as e:
        logger.warning(f"Could not load state from S3: {e}")
        return None


async def save_state_to_s3(state: MonitorState):
    """Save state to S3 for persistence between Lambda invocations."""
    bucket = os.getenv("STATE_BUCKET")
    if not bucket:
        return

    try:
        import boto3

        data = {
            "notified_performances": list(state.notified_performances),
            "last_check_times": {
                k: v.isoformat() for k, v in state.last_check_times.items()
            },
        }

        s3 = boto3.client("s3")
        s3.put_object(
            Bucket=bucket,
            Key="monitor_state.json",
            Body=json.dumps(data, ensure_ascii=False),
            ContentType="application/json",
        )
        logger.info("State saved to S3")
    except Exception as e:
        logger.warning(f"Could not save state to S3: {e}")
