"""
Seat availability checker - checks if 2 adjacent seats are available.
Uses Playwright for JavaScript-rendered seat maps.
"""
import asyncio
import logging
import re
from dataclasses import dataclass
from typing import Optional
from playwright.async_api import async_playwright, Page, Browser

from models import Performance, TicketStatus

logger = logging.getLogger(__name__)


@dataclass
class SeatCheckResult:
    """Result of checking seat availability"""
    performance: Performance
    has_adjacent_seats: bool
    adjacent_seats_count: int  # How many pairs of adjacent seats found
    total_available_seats: int
    seat_details: list[str]  # e.g., ["Rząd 5, miejsca 10-11", "Rząd 8, miejsca 3-4"]
    ticket_url: str
    error: Optional[str] = None


class SeatChecker:
    """Checks for adjacent seat availability using browser automation"""

    def __init__(self, min_adjacent_seats: int = 2):
        self.min_adjacent_seats = min_adjacent_seats
        self.browser: Optional[Browser] = None

    async def __aenter__(self):
        """Start browser"""
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(
            headless=True,
            args=[
                '--disable-blink-features=AutomationControlled',
                '--no-sandbox',
                '--disable-dev-shm-usage',
            ]
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Close browser"""
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()

    async def _create_page(self) -> Page:
        """Create a new browser page with realistic settings"""
        context = await self.browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent=(
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                'AppleWebKit/537.36 (KHTML, like Gecko) '
                'Chrome/120.0.0.0 Safari/537.36'
            ),
            locale='pl-PL',
        )
        page = await context.new_page()
        return page

    async def check_teatr_wielki_warszawa(
        self, performance: Performance
    ) -> SeatCheckResult:
        """
        Check Teatr Wielki - Opera Narodowa in Warsaw.
        Their system uses a visual seat map.
        """
        logger.info(f"Checking seats for {performance.opera_name} at Teatr Wielki Warszawa")

        page = await self._create_page()
        try:
            # Go to repertoire page first to find the specific show
            url = "https://teatrwielki.pl/repertuar/"
            await page.goto(url, wait_until='networkidle', timeout=30000)
            await asyncio.sleep(2)

            # Look for the specific opera in repertoire and try to click on it
            opera_links = await page.query_selector_all(f'a:has-text("{performance.opera_name}")')

            if opera_links:
                # Click on the first matching link
                try:
                    await opera_links[0].click()
                    await page.wait_for_load_state('networkidle', timeout=10000)
                    await asyncio.sleep(2)
                except:
                    pass

            # Now look for "Kup bilet" or ticket buttons
            ticket_buttons = await page.query_selector_all(
                'a:has-text("kup bilet"), a:has-text("Kup bilet"), '
                'button:has-text("kup"), a:has-text("bilety"), '
                '.buy-ticket, .ticket-btn, [href*="bilety"]'
            )

            if ticket_buttons:
                try:
                    await ticket_buttons[0].click()
                    await page.wait_for_load_state('networkidle', timeout=10000)
                    await asyncio.sleep(3)
                except:
                    pass

            # Look for available seats
            # Teatr Wielki uses various selectors for seats
            available_seats = []
            adjacent_pairs = []

            # Try to find seat elements
            seat_selectors = [
                '.seat.available',
                '.seat--available',
                '[data-available="true"]',
                '.miejsce.wolne',
                '.seat:not(.occupied):not(.sold)',
                'svg rect.available',
                'svg circle.available',
            ]

            for selector in seat_selectors:
                seats = await page.query_selector_all(selector)
                if seats:
                    logger.info(f"Found {len(seats)} available seats with selector: {selector}")
                    for seat in seats:
                        seat_id = await seat.get_attribute('data-seat') or await seat.get_attribute('id')
                        if seat_id:
                            available_seats.append(seat_id)
                    break

            # If no specific seat map, look for availability text
            if not available_seats:
                content = await page.content()

                # Check for "available" indicators
                availability_patterns = [
                    r'dostępn\w+\s*:\s*(\d+)',
                    r'wolnych?\s+miejsc?\w*\s*:\s*(\d+)',
                    r'(\d+)\s+bilet\w*\s+dostępn',
                    r'pozostało\s*:\s*(\d+)',
                ]

                for pattern in availability_patterns:
                    match = re.search(pattern, content, re.IGNORECASE)
                    if match:
                        count = int(match.group(1))
                        logger.info(f"Found availability indicator: {count} seats")
                        # If more than 2 seats available, assume adjacent possible
                        if count >= self.min_adjacent_seats:
                            return SeatCheckResult(
                                performance=performance,
                                has_adjacent_seats=True,
                                adjacent_seats_count=count // 2,
                                total_available_seats=count,
                                seat_details=[f"~{count} miejsc dostępnych"],
                                ticket_url=url,
                            )

                # Check for "sold out" indicators
                if any(kw in content.lower() for kw in ['wyprzedane', 'brak biletów', 'sold out']):
                    return SeatCheckResult(
                        performance=performance,
                        has_adjacent_seats=False,
                        adjacent_seats_count=0,
                        total_available_seats=0,
                        seat_details=["WYPRZEDANE"],
                        ticket_url=page.url,
                    )

                # Check for "kup bilet" button - if present, tickets likely available
                buy_buttons = await page.query_selector_all(
                    'a:has-text("kup bilet"), button:has-text("kup"), '
                    'a:has-text("dodaj do koszyka"), .add-to-cart'
                )

                if buy_buttons:
                    logger.info(f"Found buy button - tickets likely available")
                    return SeatCheckResult(
                        performance=performance,
                        has_adjacent_seats=True,  # Assume adjacent available if tickets exist
                        adjacent_seats_count=1,
                        total_available_seats=-1,  # Unknown
                        seat_details=["Bilety dostępne - sprawdź szczegóły na stronie"],
                        ticket_url=page.url,
                    )

            # Analyze adjacent seats if we have seat data
            if available_seats:
                adjacent_pairs = self._find_adjacent_seats(available_seats)

                return SeatCheckResult(
                    performance=performance,
                    has_adjacent_seats=len(adjacent_pairs) > 0,
                    adjacent_seats_count=len(adjacent_pairs),
                    total_available_seats=len(available_seats),
                    seat_details=adjacent_pairs[:5],  # Top 5 pairs
                    ticket_url=page.url,
                )

            # Fallback: if we can't determine, assume NOT available to avoid false positives
            return SeatCheckResult(
                performance=performance,
                has_adjacent_seats=False,
                adjacent_seats_count=0,
                total_available_seats=0,
                seat_details=["Nie udało się sprawdzić - sprawdź ręcznie"],
                ticket_url=page.url,
            )

        except Exception as e:
            logger.error(f"Error checking Teatr Wielki: {e}")
            return SeatCheckResult(
                performance=performance,
                has_adjacent_seats=False,
                adjacent_seats_count=0,
                total_available_seats=0,
                seat_details=[],
                ticket_url=performance.ticket_url or "",
                error=str(e),
            )
        finally:
            await page.close()

    async def check_generic_opera(
        self, performance: Performance
    ) -> SeatCheckResult:
        """
        Generic seat checker for other opera houses.
        Looks for common patterns in ticket pages.
        """
        logger.info(f"Checking seats for {performance.opera_name} at {performance.opera_house}")

        page = await self._create_page()
        try:
            url = performance.ticket_url
            if not url:
                return SeatCheckResult(
                    performance=performance,
                    has_adjacent_seats=False,
                    adjacent_seats_count=0,
                    total_available_seats=0,
                    seat_details=[],
                    ticket_url="",
                    error="No ticket URL available",
                )

            await page.goto(url, wait_until='networkidle', timeout=30000)
            await asyncio.sleep(2)

            content = await page.content()
            text = await page.inner_text('body')

            # Look for availability indicators
            available_count = 0

            # Pattern: "X biletów dostępnych" or similar
            patterns = [
                r'(\d+)\s*bilet\w*\s*dostępn',
                r'dostępn\w*\s*(\d+)',
                r'wolnych?\s*miejsc\w*\s*(\d+)',
                r'(\d+)\s*wolnych?\s*miejsc',
                r'pozostało\s*(\d+)',
                r'available\s*:\s*(\d+)',
            ]

            for pattern in patterns:
                match = re.search(pattern, text, re.IGNORECASE)
                if match:
                    available_count = int(match.group(1))
                    break

            # Check for sold out
            sold_out_keywords = ['wyprzedane', 'brak biletów', 'sold out', 'niedostępne']
            is_sold_out = any(kw in text.lower() for kw in sold_out_keywords)

            if is_sold_out:
                return SeatCheckResult(
                    performance=performance,
                    has_adjacent_seats=False,
                    adjacent_seats_count=0,
                    total_available_seats=0,
                    seat_details=["WYPRZEDANE"],
                    ticket_url=url,
                )

            # Check for "kup bilet" button as indicator of availability
            buy_buttons = await page.query_selector_all(
                'a:has-text("kup"), button:has-text("kup"), '
                'a:has-text("rezerwuj"), button:has-text("rezerwuj"), '
                'a:has-text("bilety"), .buy-button, .ticket-button'
            )

            if buy_buttons or available_count >= self.min_adjacent_seats:
                # Tickets seem available
                return SeatCheckResult(
                    performance=performance,
                    has_adjacent_seats=available_count >= self.min_adjacent_seats or len(buy_buttons) > 0,
                    adjacent_seats_count=max(1, available_count // 2) if available_count else (1 if buy_buttons else 0),
                    total_available_seats=available_count if available_count else -1,  # -1 = unknown
                    seat_details=[
                        f"{available_count} miejsc dostępnych" if available_count
                        else "Bilety prawdopodobnie dostępne"
                    ],
                    ticket_url=url,
                )

            return SeatCheckResult(
                performance=performance,
                has_adjacent_seats=False,
                adjacent_seats_count=0,
                total_available_seats=0,
                seat_details=["Status nieznany - sprawdź ręcznie"],
                ticket_url=url,
            )

        except Exception as e:
            logger.error(f"Error checking {performance.opera_house}: {e}")
            return SeatCheckResult(
                performance=performance,
                has_adjacent_seats=False,
                adjacent_seats_count=0,
                total_available_seats=0,
                seat_details=[],
                ticket_url=performance.ticket_url or "",
                error=str(e),
            )
        finally:
            await page.close()

    def _find_adjacent_seats(self, seat_ids: list[str]) -> list[str]:
        """
        Find pairs of adjacent seats from seat IDs.
        Assumes seat IDs are like "row-5-seat-10" or "R5M10" etc.
        """
        adjacent_pairs = []

        # Try to parse seat positions
        seats_by_row: dict[str, list[int]] = {}

        for seat_id in seat_ids:
            # Try various patterns
            patterns = [
                r'r(?:ow|zad)?[-_]?(\d+)[-_]?(?:s(?:eat)?|m(?:iejsce)?)[-_]?(\d+)',
                r'(\d+)[-_](\d+)',
                r'r(\d+)m(\d+)',
            ]

            for pattern in patterns:
                match = re.search(pattern, seat_id, re.IGNORECASE)
                if match:
                    row = match.group(1)
                    seat = int(match.group(2))
                    if row not in seats_by_row:
                        seats_by_row[row] = []
                    seats_by_row[row].append(seat)
                    break

        # Find adjacent seats in each row
        for row, seats in seats_by_row.items():
            seats.sort()
            for i in range(len(seats) - 1):
                if seats[i + 1] - seats[i] == 1:
                    adjacent_pairs.append(f"Rząd {row}, miejsca {seats[i]}-{seats[i+1]}")

        return adjacent_pairs

    async def check_performance(self, performance: Performance) -> SeatCheckResult:
        """Check seat availability for a performance"""
        opera_house = performance.opera_house.lower()

        if "teatr wielki" in opera_house and "warszawa" in performance.city.lower():
            return await self.check_teatr_wielki_warszawa(performance)
        else:
            return await self.check_generic_opera(performance)


async def check_seats_for_performances(
    performances: list[Performance],
    min_adjacent: int = 2
) -> list[SeatCheckResult]:
    """Check seat availability for multiple performances"""
    if not performances:
        return []

    results = []

    async with SeatChecker(min_adjacent_seats=min_adjacent) as checker:
        for perf in performances:
            try:
                result = await checker.check_performance(perf)
                results.append(result)

                # Small delay to avoid overwhelming servers
                await asyncio.sleep(1)
            except Exception as e:
                logger.error(f"Error checking {perf.opera_house}: {e}")
                results.append(SeatCheckResult(
                    performance=perf,
                    has_adjacent_seats=False,
                    adjacent_seats_count=0,
                    total_available_seats=0,
                    seat_details=[],
                    ticket_url=perf.ticket_url or "",
                    error=str(e),
                ))

    return results
