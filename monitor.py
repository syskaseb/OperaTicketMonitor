"""
Main monitoring loop for Opera Ticket Monitor
Now with adjacent seat checking!
"""
import asyncio
import logging
import signal
import sys
from datetime import datetime
from typing import Optional

from config import get_config, AppConfig
from models import MonitorState, Performance, TicketStatus
from notifier import EmailNotifier
from scrapers import scrape_all_operas
from seat_checker import check_seats_for_performances, SeatCheckResult

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("opera_monitor.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)


class OperaTicketMonitor:
    """Main monitoring orchestrator"""

    def __init__(
        self,
        config: Optional[AppConfig] = None,
        min_adjacent_seats: int = 2,
        check_seats: bool = True,
    ):
        self.config = config or get_config()
        self.state = MonitorState.load(self.config.state_file)
        self.notifier = EmailNotifier(self.config.email)
        self.running = True
        self.min_adjacent_seats = min_adjacent_seats
        self.check_seats = check_seats  # Whether to do deep seat checking
        self._setup_signal_handlers()

    def _setup_signal_handlers(self):
        """Setup graceful shutdown handlers"""

        def shutdown_handler(signum, frame):
            logger.info(f"Received signal {signum}, shutting down gracefully...")
            self.running = False

        signal.signal(signal.SIGINT, shutdown_handler)
        signal.signal(signal.SIGTERM, shutdown_handler)

    async def check_once(self) -> list[SeatCheckResult]:
        """Perform a single check of all opera houses"""
        logger.info("=" * 60)
        logger.info(f"Starting check at {datetime.now().isoformat()}")
        logger.info(f"Looking for: {self.min_adjacent_seats} adjacent seats")
        logger.info("=" * 60)

        # Step 1: Scrape all opera houses for Halka/Straszny Dwór
        results = await scrape_all_operas(
            self.config.opera_houses, self.config.monitor
        )

        all_performances: list[Performance] = []

        for result in results:
            if result.success:
                logger.info(
                    f"✓ {result.opera_house} ({result.city}): "
                    f"Found {len(result.performances)} target performances"
                )
                all_performances.extend(result.performances)
            else:
                logger.warning(
                    f"✗ {result.opera_house} ({result.city}): {result.error_message}"
                )

            self.state.last_check_times[result.opera_house] = datetime.now()

        logger.info("-" * 60)
        logger.info(f"Total performances found: {len(all_performances)}")

        if not all_performances:
            logger.info("No performances found. Nothing to check.")
            return []

        # Step 2: Check seat availability for each performance
        seat_results: list[SeatCheckResult] = []

        if self.check_seats:
            logger.info("=" * 60)
            logger.info("CHECKING SEAT AVAILABILITY...")
            logger.info("=" * 60)

            seat_results = await check_seats_for_performances(
                all_performances,
                min_adjacent=self.min_adjacent_seats
            )

            # Filter to only performances with adjacent seats
            performances_with_seats = [
                r for r in seat_results if r.has_adjacent_seats
            ]

            logger.info("-" * 60)
            logger.info(f"Performances with {self.min_adjacent_seats}+ adjacent seats: {len(performances_with_seats)}")

            for r in performances_with_seats:
                logger.info(
                    f"  ✓ {r.performance.opera_name} @ {r.performance.opera_house} - "
                    f"{r.adjacent_seats_count} pairs available"
                )
        else:
            # If not checking seats, convert performances to seat results
            seat_results = [
                SeatCheckResult(
                    performance=p,
                    has_adjacent_seats=True,  # Assume available
                    adjacent_seats_count=-1,
                    total_available_seats=-1,
                    seat_details=["Seat check disabled"],
                    ticket_url=p.ticket_url or "",
                )
                for p in all_performances
            ]
            performances_with_seats = seat_results

        # Step 3: Send notifications for NEW performances with adjacent seats
        new_results = [
            r for r in performances_with_seats
            if self.state.should_notify(r.performance)
        ]

        if new_results:
            logger.info("=" * 60)
            logger.info(f"NEW! Found {len(new_results)} performances with adjacent seats!")
            logger.info("=" * 60)

            for r in new_results:
                logger.info(
                    f"  🎭 {r.performance.opera_name}"
                )
                logger.info(
                    f"     📍 {r.performance.opera_house} ({r.performance.city})"
                )
                logger.info(
                    f"     📅 {r.performance.date_str or 'TBD'} {r.performance.time}"
                )
                logger.info(
                    f"     🎫 {r.ticket_url}"
                )
                if r.seat_details:
                    logger.info(f"     💺 {', '.join(r.seat_details)}")

            # Send notification
            success = self.notifier.send_seat_notification(
                new_results,
                min_adjacent=self.min_adjacent_seats
            )

            if success:
                for r in new_results:
                    self.state.mark_notified(r.performance)
                self.state.save(self.config.state_file)
                logger.info("Notification sent successfully!")
            else:
                logger.warning("Failed to send notification")
        else:
            logger.info("No new performances with adjacent seats to notify about.")

        return seat_results

    async def run_forever(self):
        """Run the monitor continuously"""
        logger.info("=" * 60)
        logger.info("🎭 OPERA TICKET MONITOR STARTED")
        logger.info("=" * 60)
        logger.info(f"Szukam: Halka, Straszny Dwór")
        logger.info(f"Wymagane: {self.min_adjacent_seats} miejsca obok siebie")
        logger.info(f"Sprawdzanie co: {self.config.monitor.check_interval_minutes} minut")
        logger.info(f"Powiadomienia na: {', '.join(self.config.email.recipient_emails)}")
        logger.info(f"Monitorowane opery: {len([h for h in self.config.opera_houses if h.enabled])}")
        logger.info("=" * 60)

        # Send startup notification
        self.notifier.send_startup_notification()

        check_count = 0
        consecutive_errors = 0

        while self.running:
            check_count += 1
            logger.info(f"\n🔍 Check #{check_count}")

            try:
                await self.check_once()
                consecutive_errors = 0

            except Exception as e:
                logger.error(f"Error during check: {e}", exc_info=True)
                consecutive_errors += 1

                if consecutive_errors >= 3:
                    self.notifier.send_error_notification(
                        f"Monitor experienced {consecutive_errors} consecutive errors.\n"
                        f"Last error: {str(e)}"
                    )

            # Wait for next check
            if self.running:
                next_check = datetime.now().timestamp() + (
                    self.config.monitor.check_interval_minutes * 60
                )
                logger.info(
                    f"\n⏰ Next check in {self.config.monitor.check_interval_minutes} minutes "
                    f"(at {datetime.fromtimestamp(next_check).strftime('%H:%M:%S')})"
                )

                sleep_seconds = self.config.monitor.check_interval_minutes * 60
                for _ in range(sleep_seconds):
                    if not self.running:
                        break
                    await asyncio.sleep(1)

        self.state.save(self.config.state_file)
        logger.info("Monitor stopped. State saved.")

    async def run_once(self):
        """Run a single check (useful for testing or Lambda)"""
        return await self.check_once()


async def main():
    """Main entry point"""
    monitor = OperaTicketMonitor(
        min_adjacent_seats=2,  # Szukamy 2 miejsc obok siebie
        check_seats=True,
    )
    await monitor.run_forever()


if __name__ == "__main__":
    asyncio.run(main())
