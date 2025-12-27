"""
Web scrapers for Polish opera house websites
"""
import asyncio
import logging
import re
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from typing import Optional
from urllib.parse import urljoin

import aiohttp
from bs4 import BeautifulSoup

from config import OperaHouse, MonitorConfig, TARGET_OPERAS, AVAILABILITY_KEYWORDS, SOLD_OUT_KEYWORDS
from models import Performance, ScrapeResult, TicketStatus

logger = logging.getLogger(__name__)

# Polish month names for formatting
POLISH_MONTHS = {
    1: "stycznia", 2: "lutego", 3: "marca", 4: "kwietnia",
    5: "maja", 6: "czerwca", 7: "lipca", 8: "sierpnia",
    9: "września", 10: "października", 11: "listopada", 12: "grudnia"
}

POLISH_WEEKDAYS = {
    0: "Poniedziałek", 1: "Wtorek", 2: "Środa", 3: "Czwartek",
    4: "Piątek", 5: "Sobota", 6: "Niedziela"
}


def format_polish_date(dt: datetime) -> str:
    """Format date in Polish style: 'Piątek 7 lutego 2026'"""
    weekday = POLISH_WEEKDAYS[dt.weekday()]
    month = POLISH_MONTHS[dt.month]
    return f"{weekday} {dt.day} {month} {dt.year}"


def is_future_date(dt: Optional[datetime]) -> bool:
    """Check if date is today or in the future"""
    if dt is None:
        return False  # Exclude performances with unknown dates
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    return dt >= today


def is_available(status: TicketStatus) -> bool:
    """Check if tickets are confirmed available (not sold out, not unknown)"""
    return status == TicketStatus.AVAILABLE or status == TicketStatus.LIMITED


class BaseScraper(ABC):
    """Base class for opera house scrapers"""

    def __init__(self, opera_house: OperaHouse, config: MonitorConfig):
        self.opera_house = opera_house
        self.config = config
        self.session: Optional[aiohttp.ClientSession] = None

    def _get_headers(self) -> dict:
        """Get request headers"""
        return {
            "User-Agent": self.config.user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "pl-PL,pl;q=0.9,en;q=0.8",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
        }

    async def fetch_page(self, url: str) -> Optional[str]:
        """Fetch a webpage with retries"""
        for attempt in range(self.config.max_retries):
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(
                        url,
                        headers=self._get_headers(),
                        timeout=aiohttp.ClientTimeout(total=self.config.request_timeout_seconds),
                        ssl=False  # Some opera sites have SSL issues
                    ) as response:
                        if response.status == 200:
                            return await response.text()
                        else:
                            logger.warning(
                                f"Got status {response.status} from {url}"
                            )
            except asyncio.TimeoutError:
                logger.warning(f"Timeout fetching {url}, attempt {attempt + 1}")
            except aiohttp.ClientError as e:
                logger.warning(f"Error fetching {url}: {e}, attempt {attempt + 1}")
            except Exception as e:
                logger.error(f"Unexpected error fetching {url}: {e}")

            if attempt < self.config.max_retries - 1:
                await asyncio.sleep(self.config.retry_delay_seconds)

        return None

    def _is_target_opera(self, text: str) -> Optional[str]:
        """Check if text contains a target opera name"""
        text_lower = text.lower()
        for opera in TARGET_OPERAS:
            if opera.lower() in text_lower:
                # Return normalized name
                if "straszny" in text_lower:
                    return "Straszny Dwór"
                elif "halka" in text_lower:
                    return "Halka"
        return None

    def _detect_availability(self, text: str) -> TicketStatus:
        """Detect ticket availability from text"""
        text_lower = text.lower()

        for keyword in SOLD_OUT_KEYWORDS:
            if keyword in text_lower:
                return TicketStatus.SOLD_OUT

        for keyword in AVAILABILITY_KEYWORDS:
            if keyword in text_lower:
                return TicketStatus.AVAILABLE

        return TicketStatus.UNKNOWN

    def _parse_polish_date(self, date_str: str) -> Optional[datetime]:
        """Parse Polish date formats"""
        # Common Polish date formats
        patterns = [
            (r"(\d{1,2})\.(\d{1,2})\.(\d{4})", "%d.%m.%Y"),
            (r"(\d{1,2})/(\d{1,2})/(\d{4})", "%d/%m/%Y"),
            (r"(\d{4})-(\d{2})-(\d{2})", "%Y-%m-%d"),
            (r"(\d{1,2}) (\w+) (\d{4})", None),  # "15 stycznia 2025"
        ]

        polish_months = {
            "stycznia": 1, "lutego": 2, "marca": 3, "kwietnia": 4,
            "maja": 5, "czerwca": 6, "lipca": 7, "sierpnia": 8,
            "września": 9, "października": 10, "listopada": 11, "grudnia": 12,
            "styczeń": 1, "luty": 2, "marzec": 3, "kwiecień": 4,
            "maj": 5, "czerwiec": 6, "lipiec": 7, "sierpień": 8,
            "wrzesień": 9, "październik": 10, "listopad": 11, "grudzień": 12,
        }

        for pattern, date_format in patterns:
            match = re.search(pattern, date_str)
            if match:
                if date_format:
                    try:
                        # Reconstruct date string for parsing
                        date_part = match.group(0)
                        return datetime.strptime(date_part, date_format)
                    except ValueError:
                        continue
                else:
                    # Handle Polish month names
                    try:
                        day = int(match.group(1))
                        month_name = match.group(2).lower()
                        year = int(match.group(3))
                        month = polish_months.get(month_name)
                        if month:
                            return datetime(year, month, day)
                    except (ValueError, KeyError):
                        continue

        return None

    @abstractmethod
    async def scrape(self) -> ScrapeResult:
        """Scrape the opera house website"""
        pass


class GenericOperaScraper(BaseScraper):
    """
    Generic scraper that works for most Polish opera websites.
    They typically have similar structures.
    """

    async def scrape(self) -> ScrapeResult:
        """Scrape the opera house website"""
        logger.info(f"Scraping {self.opera_house.name} ({self.opera_house.city})")

        html = await self.fetch_page(self.opera_house.repertoire_url)

        if not html:
            return ScrapeResult(
                opera_house=self.opera_house.name,
                city=self.opera_house.city,
                success=False,
                error_message="Failed to fetch repertoire page",
            )

        try:
            performances = self._parse_repertoire(html)
            # Filter to only future dates AND available tickets
            valid_performances = [
                p for p in performances
                if is_future_date(p.date) and is_available(p.status)
            ]
            return ScrapeResult(
                opera_house=self.opera_house.name,
                city=self.opera_house.city,
                success=True,
                performances=valid_performances,
            )
        except Exception as e:
            logger.error(f"Error parsing {self.opera_house.name}: {e}")
            return ScrapeResult(
                opera_house=self.opera_house.name,
                city=self.opera_house.city,
                success=False,
                error_message=str(e),
            )

    def _parse_repertoire(self, html: str) -> list[Performance]:
        """Parse repertoire page and find target operas"""
        soup = BeautifulSoup(html, "html.parser")
        performances = []

        # Look for common patterns in Polish opera websites
        # Most use divs/articles with classes like: event, spektakl, show, performance, repertuar-item

        # Common container patterns
        event_selectors = [
            "article",
            ".event",
            ".spektakl",
            ".show",
            ".performance",
            ".repertuar-item",
            ".repertoire-item",
            ".calendar-event",
            ".event-item",
            ".program-item",
            "[class*='event']",
            "[class*='spektakl']",
            "[class*='repertuar']",
            "li",  # Sometimes events are in lists
        ]

        found_containers = []
        for selector in event_selectors:
            containers = soup.select(selector)
            if containers:
                found_containers.extend(containers)

        # Deduplicate
        seen = set()
        unique_containers = []
        for c in found_containers:
            c_id = id(c)
            if c_id not in seen:
                seen.add(c_id)
                unique_containers.append(c)

        for container in unique_containers:
            text = container.get_text(separator=" ", strip=True)
            opera_name = self._is_target_opera(text)

            if opera_name:
                performance = self._extract_performance_details(
                    container, opera_name, text
                )
                if performance:
                    performances.append(performance)

        # Also search the entire page for mentions
        # (in case the structure is unusual)
        full_text = soup.get_text(separator=" ", strip=True)
        for target in TARGET_OPERAS:
            if target.lower() in full_text.lower():
                logger.info(
                    f"Found mention of '{target}' at {self.opera_house.name}"
                )

        # Remove duplicates
        unique_performances = list(set(performances))
        return unique_performances

    def _extract_performance_details(
        self, container, opera_name: str, text: str
    ) -> Optional[Performance]:
        """Extract performance details from a container element"""

        # Try to find date
        date_str = ""
        date = None

        # Look for date in various elements
        date_elements = container.select(
            ".date, .data, time, .event-date, .spektakl-date, [class*='date'], [class*='data']"
        )
        for elem in date_elements:
            potential_date = elem.get_text(strip=True)
            parsed = self._parse_polish_date(potential_date)
            if parsed:
                date = parsed
                date_str = potential_date
                break

        # If not found, try to find date in text
        if not date_str:
            date_match = re.search(
                r"\d{1,2}[./]\d{1,2}[./]\d{4}|\d{1,2}\s+\w+\s+\d{4}",
                text
            )
            if date_match:
                date_str = date_match.group(0)
                date = self._parse_polish_date(date_str)

        # Try to find time
        time_str = ""
        time_match = re.search(r"(\d{1,2})[:.:](\d{2})", text)
        if time_match:
            time_str = f"{time_match.group(1)}:{time_match.group(2)}"

        # Try to find ticket link
        ticket_url = ""
        links = container.find_all("a", href=True)
        for link in links:
            href = link["href"]
            link_text = link.get_text(strip=True).lower()
            if any(
                kw in link_text or kw in href.lower()
                for kw in ["bilet", "ticket", "kup", "buy", "rezerwuj"]
            ):
                ticket_url = urljoin(self.opera_house.base_url, href)
                break

        # If no specific ticket link, use the general tickets URL
        if not ticket_url and self.opera_house.tickets_url_pattern:
            ticket_url = self.opera_house.tickets_url_pattern

        # Detect availability
        status = self._detect_availability(text)

        return Performance(
            opera_name=opera_name,
            opera_house=self.opera_house.name,
            city=self.opera_house.city,
            date=date,
            date_str=date_str,
            time=time_str,
            ticket_url=ticket_url,
            status=status,
        )


class TeatrWielkiWarszawaScraper(BaseScraper):
    """
    Specialized scraper for Teatr Wielki - Opera Narodowa in Warsaw.
    Scrapes the kalendarium (calendar) pages for all upcoming months.
    """

    async def scrape(self) -> ScrapeResult:
        """Scrape Teatr Wielki website - all months from now to June next year"""
        logger.info(f"Scraping {self.opera_house.name} ({self.opera_house.city})")

        performances = []

        # Build list of month URLs to scrape (current month + next 6 months)
        now = datetime.now()
        month_urls = []

        for i in range(7):  # Current month + 6 more months
            target_date = now + timedelta(days=i * 30)
            year = target_date.year
            month = target_date.month
            month_urls.append(
                f"https://teatrwielki.pl/kalendarium/data/{year}/{month:02d}/"
            )

        # Also include current kalendarium page
        month_urls.insert(0, "https://teatrwielki.pl/kalendarium/")

        for url in month_urls:
            html = await self.fetch_page(url)
            if html:
                performances.extend(self._parse_kalendarium(html))

        # Filter to future dates AND available tickets, remove duplicates
        valid_performances = [
            p for p in performances
            if is_future_date(p.date) and is_available(p.status)
        ]
        unique_performances = list(set(valid_performances))

        return ScrapeResult(
            opera_house=self.opera_house.name,
            city=self.opera_house.city,
            success=True,
            performances=unique_performances,
        )

    def _parse_kalendarium(self, html: str) -> list[Performance]:
        """Parse kalendarium page for target operas"""
        soup = BeautifulSoup(html, "html.parser")
        performances = []

        # Find all event items
        events = soup.select("li.data-event")

        for event in events:
            h3 = event.select_one("h3 a")
            if not h3:
                continue

            title = h3.get_text(strip=True)
            opera_name = self._is_target_opera(title)

            if not opera_name:
                continue

            href = h3.get("href", "")

            # Extract date from URL: /kalendarium/2025-2026/halka/termin/2025-12-07_18-00/
            date = None
            time_str = ""
            date_match = re.search(r"(\d{4})-(\d{2})-(\d{2})_(\d{2})-(\d{2})", href)
            if date_match:
                year, month, day, hour, minute = date_match.groups()
                date = datetime(int(year), int(month), int(day), int(hour), int(minute))
                time_str = f"{hour}:{minute}"

            # Format date in Polish
            date_str = format_polish_date(date) if date else ""

            # Build ticket URL
            ticket_url = urljoin("https://teatrwielki.pl", href) if href else "https://teatrwielki.pl/bilety/"

            # Check availability
            status = TicketStatus.UNKNOWN
            text = event.get_text(separator=" ", strip=True).lower()
            if "wyprzedane" in text or "sold out" in text:
                status = TicketStatus.SOLD_OUT
            elif "kup bilet" in text or "bilety" in text:
                status = TicketStatus.AVAILABLE

            performances.append(Performance(
                opera_name=opera_name,
                opera_house=self.opera_house.name,
                city=self.opera_house.city,
                date=date,
                date_str=date_str,
                time=time_str,
                ticket_url=ticket_url,
                status=status,
            ))

        return performances


class OperaWroclawScraper(BaseScraper):
    """Specialized scraper for Opera Wrocławska"""

    async def scrape(self) -> ScrapeResult:
        """Scrape Opera Wrocław website"""
        logger.info(f"Scraping {self.opera_house.name} ({self.opera_house.city})")

        html = await self.fetch_page(self.opera_house.repertoire_url)
        if not html:
            return ScrapeResult(
                opera_house=self.opera_house.name,
                city=self.opera_house.city,
                success=False,
                error_message="Failed to fetch page",
            )

        performances = self._parse_repertoire(html)
        valid_performances = [
            p for p in performances
            if is_future_date(p.date) and is_available(p.status)
        ]

        return ScrapeResult(
            opera_house=self.opera_house.name,
            city=self.opera_house.city,
            success=True,
            performances=list(set(valid_performances)),
        )

    def _parse_repertoire(self, html: str) -> list[Performance]:
        """Parse repertoire page"""
        soup = BeautifulSoup(html, "html.parser")
        performances = []

        # Opera Wrocław structure:
        # - Each performance is in a div.rep-single that contains BOTH the date (YYYYMMDD) AND the title
        # - The h3.rep-list-title contains the opera name
        # - The YYYYMMDD date must be in the SAME rep-single div as the h3

        # Find all rep-single containers (each is one performance)
        for rep_single in soup.find_all("div", class_="rep-single"):
            text = rep_single.get_text(separator=" ", strip=True)

            # Check if this contains a target opera
            opera_name = self._is_target_opera(text)
            if not opera_name:
                continue

            # Must have YYYYMMDD date format in THIS specific container
            date_match = re.search(r"(\d{4})(\d{2})(\d{2})", text)
            if not date_match:
                continue  # Skip if no date in this container

            year, month, day = date_match.groups()
            try:
                date = datetime(int(year), int(month), int(day))
            except ValueError:
                continue

            # Extract time
            time_str = ""
            time_match = re.search(r"(\d{1,2}):(\d{2})", text)
            if time_match:
                time_str = f"{time_match.group(1)}:{time_match.group(2)}"

            date_str = format_polish_date(date)

            # Find ticket URL - must have active "Kup bilet" link
            ticket_url = ""
            has_buy_link = False
            for link in rep_single.find_all("a", href=True):
                href = link["href"]
                link_text = link.get_text(strip=True).lower()
                if "kup" in link_text and "bilet" in link_text:
                    ticket_url = href if href.startswith("http") else urljoin(self.opera_house.base_url, href)
                    has_buy_link = True
                    break

            # Determine availability - check for "brak miejsc" (no seats) in this specific container
            text_lower = text.lower()
            if "wyprzedane" in text_lower or "brak miejsc" in text_lower or "brak biletów" in text_lower:
                status = TicketStatus.SOLD_OUT
            elif has_buy_link:
                status = TicketStatus.AVAILABLE
            else:
                status = TicketStatus.UNKNOWN

            performances.append(Performance(
                opera_name=opera_name,
                opera_house=self.opera_house.name,
                city=self.opera_house.city,
                date=date,
                date_str=date_str,
                time=time_str,
                ticket_url=ticket_url,
                status=status,
            ))

        return performances


class OperaBaltyckaGdanskScraper(BaseScraper):
    """Specialized scraper for Opera Bałtycka in Gdańsk"""

    async def scrape(self) -> ScrapeResult:
        """Scrape Opera Bałtycka website"""
        logger.info(f"Scraping {self.opera_house.name} ({self.opera_house.city})")

        html = await self.fetch_page(self.opera_house.repertoire_url)
        if not html:
            return ScrapeResult(
                opera_house=self.opera_house.name,
                city=self.opera_house.city,
                success=False,
                error_message="Failed to fetch page",
            )

        performances = self._parse_repertoire(html)
        valid_performances = [
            p for p in performances
            if is_future_date(p.date) and is_available(p.status)
        ]

        return ScrapeResult(
            opera_house=self.opera_house.name,
            city=self.opera_house.city,
            success=True,
            performances=list(set(valid_performances)),
        )

    def _parse_repertoire(self, html: str) -> list[Performance]:
        """Parse repertoire page"""
        soup = BeautifulSoup(html, "html.parser")
        performances = []

        # Opera Bałtycka format: "31 grudnia 2025 środa godz. 19:00 opera Straszny dwór"
        polish_months_reverse = {
            "stycznia": 1, "lutego": 2, "marca": 3, "kwietnia": 4,
            "maja": 5, "czerwca": 6, "lipca": 7, "sierpnia": 8,
            "września": 9, "października": 10, "listopada": 11, "grudnia": 12
        }

        for elem in soup.find_all(["div", "article", "li"]):
            text = elem.get_text(separator=" ", strip=True)
            opera_name = self._is_target_opera(text)

            if not opera_name:
                continue

            # Extract date: "31 grudnia 2025"
            date = None
            date_match = re.search(r"(\d{1,2})\s+(stycznia|lutego|marca|kwietnia|maja|czerwca|lipca|sierpnia|września|października|listopada|grudnia)\s+(\d{4})", text.lower())
            if date_match:
                day = int(date_match.group(1))
                month = polish_months_reverse.get(date_match.group(2), 1)
                year = int(date_match.group(3))
                try:
                    date = datetime(year, month, day)
                except ValueError:
                    pass

            # Extract time
            time_str = ""
            time_match = re.search(r"godz\.?\s*(\d{1,2}):(\d{2})", text)
            if time_match:
                time_str = f"{time_match.group(1)}:{time_match.group(2)}"

            date_str = format_polish_date(date) if date else ""

            # Check availability
            status = self._detect_availability(text)
            if "wyprzedane" in text.lower():
                status = TicketStatus.SOLD_OUT

            ticket_url = "https://operabaltycka.pl/bilety/"

            performances.append(Performance(
                opera_name=opera_name,
                opera_house=self.opera_house.name,
                city=self.opera_house.city,
                date=date,
                date_str=date_str,
                time=time_str,
                ticket_url=ticket_url,
                status=status,
            ))

        return performances


class OperaNovaBydgoszczScraper(BaseScraper):
    """Specialized scraper for Opera Nova in Bydgoszcz"""

    async def scrape(self) -> ScrapeResult:
        """Scrape Opera Nova website"""
        logger.info(f"Scraping {self.opera_house.name} ({self.opera_house.city})")

        html = await self.fetch_page(self.opera_house.repertoire_url)
        if not html:
            return ScrapeResult(
                opera_house=self.opera_house.name,
                city=self.opera_house.city,
                success=False,
                error_message="Failed to fetch page",
            )

        performances = self._parse_repertoire(html)
        valid_performances = [
            p for p in performances
            if is_future_date(p.date) and is_available(p.status)
        ]

        return ScrapeResult(
            opera_house=self.opera_house.name,
            city=self.opera_house.city,
            success=True,
            performances=list(set(valid_performances)),
        )

    def _parse_repertoire(self, html: str) -> list[Performance]:
        """Parse repertoire page"""
        soup = BeautifulSoup(html, "html.parser")
        performances = []

        # Opera Nova format: "09 STRASZNY DWÓR Opera 19:00"
        # They show by month, need to figure out which month
        now = datetime.now()
        current_month = now.month
        current_year = now.year

        for elem in soup.find_all(["div", "article", "li", "a"]):
            text = elem.get_text(separator=" ", strip=True)
            opera_name = self._is_target_opera(text)

            if not opera_name:
                continue

            # Extract day number at start
            date = None
            day_match = re.search(r"^(\d{1,2})\s", text)
            if day_match:
                day = int(day_match.group(1))
                # Assume next occurrence of this day
                try:
                    date = datetime(current_year, current_month, day)
                    if date < now:
                        # Try next month
                        next_month = current_month + 1
                        next_year = current_year
                        if next_month > 12:
                            next_month = 1
                            next_year += 1
                        date = datetime(next_year, next_month, day)
                except ValueError:
                    pass

            # Extract time
            time_str = ""
            time_match = re.search(r"(\d{1,2}):(\d{2})", text)
            if time_match:
                time_str = f"{time_match.group(1)}:{time_match.group(2)}"

            date_str = format_polish_date(date) if date else ""

            status = self._detect_availability(text)

            ticket_url = "https://opera.bydgoszcz.pl/bilety.html"

            performances.append(Performance(
                opera_name=opera_name,
                opera_house=self.opera_house.name,
                city=self.opera_house.city,
                date=date,
                date_str=date_str,
                time=time_str,
                ticket_url=ticket_url,
                status=status,
            ))

        return performances


def get_scraper(opera_house: OperaHouse, config: MonitorConfig) -> BaseScraper:
    """Get appropriate scraper for an opera house"""

    # Use specialized scrapers for specific theaters
    specialized_scrapers = {
        "Teatr Wielki - Opera Narodowa": TeatrWielkiWarszawaScraper,
        "Opera Wrocławska": OperaWroclawScraper,
        "Opera Bałtycka": OperaBaltyckaGdanskScraper,
        "Opera Nova": OperaNovaBydgoszczScraper,
    }

    scraper_class = specialized_scrapers.get(opera_house.name, GenericOperaScraper)
    return scraper_class(opera_house, config)


async def scrape_all_operas(
    opera_houses: list[OperaHouse], config: MonitorConfig
) -> list[ScrapeResult]:
    """Scrape all opera houses concurrently"""
    scrapers = [
        get_scraper(house, config)
        for house in opera_houses
        if house.enabled
    ]

    # Run all scrapers concurrently
    tasks = [scraper.scrape() for scraper in scrapers]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    # Handle exceptions
    processed_results = []
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            logger.error(f"Scraper failed with exception: {result}")
            processed_results.append(
                ScrapeResult(
                    opera_house=scrapers[i].opera_house.name,
                    city=scrapers[i].opera_house.city,
                    success=False,
                    error_message=str(result),
                )
            )
        else:
            processed_results.append(result)

    return processed_results
