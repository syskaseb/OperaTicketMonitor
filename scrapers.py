"""
Web scrapers for Polish opera house websites
"""
import asyncio
import logging
import re
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Optional
from urllib.parse import urljoin

import aiohttp
from bs4 import BeautifulSoup

from config import OperaHouse, MonitorConfig, TARGET_OPERAS, AVAILABILITY_KEYWORDS, SOLD_OUT_KEYWORDS
from models import Performance, ScrapeResult, TicketStatus

logger = logging.getLogger(__name__)


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
            return ScrapeResult(
                opera_house=self.opera_house.name,
                city=self.opera_house.city,
                success=True,
                performances=performances,
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
    They have a more complex website structure.
    """

    async def scrape(self) -> ScrapeResult:
        """Scrape Teatr Wielki website"""
        logger.info(f"Scraping {self.opera_house.name} ({self.opera_house.city})")

        performances = []

        # Try repertoire page
        html = await self.fetch_page(self.opera_house.repertoire_url)

        if html:
            performances.extend(self._parse_page(html))

        # Also try the calendar/schedule pages
        calendar_urls = [
            "https://teatrwielki.pl/kalendarium/",
            "https://teatrwielki.pl/spektakle/",
        ]

        for url in calendar_urls:
            html = await self.fetch_page(url)
            if html:
                performances.extend(self._parse_page(html))

        # Remove duplicates
        unique_performances = list(set(performances))

        if unique_performances or html:
            return ScrapeResult(
                opera_house=self.opera_house.name,
                city=self.opera_house.city,
                success=True,
                performances=unique_performances,
            )
        else:
            return ScrapeResult(
                opera_house=self.opera_house.name,
                city=self.opera_house.city,
                success=False,
                error_message="Failed to fetch any pages",
            )

    def _parse_page(self, html: str) -> list[Performance]:
        """Parse a page for target operas"""
        soup = BeautifulSoup(html, "html.parser")
        performances = []

        # Teatr Wielki uses various selectors
        selectors = [
            ".schedule-item",
            ".repertoire-item",
            ".event",
            ".performance",
            "article",
            ".calendar-item",
            "[data-event]",
        ]

        for selector in selectors:
            items = soup.select(selector)
            for item in items:
                text = item.get_text(separator=" ", strip=True)
                opera_name = self._is_target_opera(text)

                if opera_name:
                    performance = self._extract_performance(item, opera_name, text)
                    if performance:
                        performances.append(performance)

        return performances

    def _extract_performance(
        self, element, opera_name: str, text: str
    ) -> Optional[Performance]:
        """Extract performance details"""
        # Extract date
        date_str = ""
        date = None

        date_elem = element.select_one(".date, time, .event-date")
        if date_elem:
            date_str = date_elem.get_text(strip=True)
            date = self._parse_polish_date(date_str)

        # Extract time
        time_str = ""
        time_match = re.search(r"(\d{1,2})[:.:](\d{2})", text)
        if time_match:
            time_str = f"{time_match.group(1)}:{time_match.group(2)}"

        # Find ticket URL
        ticket_url = ""
        for link in element.find_all("a", href=True):
            href = link["href"]
            if "bilet" in href.lower() or "ticket" in href.lower():
                ticket_url = urljoin(self.opera_house.base_url, href)
                break

        if not ticket_url:
            ticket_url = "https://teatrwielki.pl/bilety/"

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


def get_scraper(opera_house: OperaHouse, config: MonitorConfig) -> BaseScraper:
    """Get appropriate scraper for an opera house"""

    # Use specialized scrapers for specific theaters
    specialized_scrapers = {
        "Teatr Wielki - Opera Narodowa": TeatrWielkiWarszawaScraper,
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
