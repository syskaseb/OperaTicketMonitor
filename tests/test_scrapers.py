"""Integration tests for scrapers with mocked HTTP responses"""
import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch, MagicMock

from aioresponses import aioresponses

from scrapers import (
    TeatrWielkiWarszawaScraper,
    OperaWroclawScraper,
    OperaBaltyckaGdanskScraper,
    GenericOperaScraper,
)
from config import OperaHouse, MonitorConfig
from models import TicketStatus


def future_date(days_ahead: int = 30) -> datetime:
    """Generate a future date for testing"""
    return datetime.now() + timedelta(days=days_ahead)


def format_date_yyyymmdd(dt: datetime) -> str:
    """Format date as YYYYMMDD"""
    return dt.strftime("%Y%m%d")


def format_date_iso(dt: datetime) -> str:
    """Format date as YYYY-MM-DD"""
    return dt.strftime("%Y-%m-%d")


def format_date_polish(dt: datetime) -> str:
    """Format date in Polish style: '31 stycznia 2026'"""
    polish_months = {
        1: "stycznia", 2: "lutego", 3: "marca", 4: "kwietnia",
        5: "maja", 6: "czerwca", 7: "lipca", 8: "sierpnia",
        9: "września", 10: "października", 11: "listopada", 12: "grudnia"
    }
    polish_weekdays = {
        0: "poniedziałek", 1: "wtorek", 2: "środa", 3: "czwartek",
        4: "piątek", 5: "sobota", 6: "niedziela"
    }
    return f"{dt.day} {polish_months[dt.month]} {dt.year} {polish_weekdays[dt.weekday()]} godz. 19:00"


@pytest.fixture
def config():
    """Fast config for tests with minimal retries"""
    cfg = MonitorConfig()
    cfg.max_retries = 1
    cfg.retry_delay_seconds = 0
    cfg.request_timeout_seconds = 5
    return cfg


@pytest.fixture
def teatr_wielki_house():
    return OperaHouse(
        name="Teatr Wielki - Opera Narodowa",
        city="Warszawa",
        base_url="https://teatrwielki.pl",
        repertoire_url="https://teatrwielki.pl/repertuar/",
    )


@pytest.fixture
def opera_wroclaw_house():
    return OperaHouse(
        name="Opera Wrocławska",
        city="Wrocław",
        base_url="https://www.opera.wroclaw.pl",
        repertoire_url="https://www.opera.wroclaw.pl/1/repertuar.php",
    )


@pytest.fixture
def opera_baltycka_house():
    return OperaHouse(
        name="Opera Bałtycka",
        city="Gdańsk",
        base_url="https://operabaltycka.pl",
        repertoire_url="https://operabaltycka.pl/repertuar/",
    )


class TestTeatrWielkiWarszawaScraper:
    """Tests for Teatr Wielki Warsaw scraper"""

    @pytest.mark.asyncio
    async def test_parses_halka_from_kalendarium(self, teatr_wielki_house, config):
        """Test parsing Halka performance from kalendarium page"""
        test_date = future_date(60)
        date_str = f"{format_date_iso(test_date)}_19-00"

        html = f"""
        <html>
        <body>
            <ul>
                <li class="data-event">
                    <h3><a href="/kalendarium/2025-2026/halka/termin/{date_str}/">Halka</a></h3>
                    <span>Kup bilet</span>
                </li>
            </ul>
        </body>
        </html>
        """

        scraper = TeatrWielkiWarszawaScraper(teatr_wielki_house, config)

        with aioresponses() as mocked:
            # Mock all kalendarium URLs
            mocked.get("https://teatrwielki.pl/kalendarium/", body=html)
            for i in range(7):
                target_date = datetime.now()
                year = target_date.year + (i // 12)
                month = ((target_date.month + i - 1) % 12) + 1
                mocked.get(
                    f"https://teatrwielki.pl/kalendarium/data/{year}/{month:02d}/",
                    body=html,
                )

            result = await scraper.scrape()

        assert result.success is True
        assert len(result.performances) >= 1

        halka = next((p for p in result.performances if p.opera_name == "Halka"), None)
        assert halka is not None
        assert halka.date.year == test_date.year
        assert halka.date.month == test_date.month
        assert halka.date.day == test_date.day

    @pytest.mark.asyncio
    async def test_filters_sold_out_performances(self, teatr_wielki_house, config):
        """Test that sold out performances are filtered"""
        test_date = future_date(60)
        date_str = f"{format_date_iso(test_date)}_19-00"

        html = f"""
        <html>
        <body>
            <ul>
                <li class="data-event">
                    <h3><a href="/kalendarium/2025-2026/halka/termin/{date_str}/">Halka</a></h3>
                    <span>wyprzedane</span>
                </li>
            </ul>
        </body>
        </html>
        """

        scraper = TeatrWielkiWarszawaScraper(teatr_wielki_house, config)

        with aioresponses() as mocked:
            mocked.get("https://teatrwielki.pl/kalendarium/", body=html)
            for i in range(7):
                target_date = datetime.now()
                year = target_date.year + (i // 12)
                month = ((target_date.month + i - 1) % 12) + 1
                mocked.get(
                    f"https://teatrwielki.pl/kalendarium/data/{year}/{month:02d}/",
                    body=html,
                )

            result = await scraper.scrape()

        # Sold out should be filtered
        assert result.success is True
        assert len(result.performances) == 0


class TestOperaWroclawScraper:
    """Tests for Opera Wrocław scraper"""

    @pytest.mark.asyncio
    async def test_parses_halka_with_correct_date(self, opera_wroclaw_house, config):
        """Test that Opera Wrocław correctly parses dates from rep-single containers"""
        test_date = future_date(45)
        yyyymmdd = format_date_yyyymmdd(test_date)

        html = f"""
        <html>
        <body>
            <div class="rep-single list">
                <span>7 maja, Cz 19:00 {yyyymmdd}</span>
                <h3 class="rep-list-title">Halka</h3>
                <a href="https://bilety.opera.wroclaw.pl/rezerwacja/?id=123">Kup bilet</a>
            </div>
            <div class="rep-single list">
                <span>31 grudnia, Śr 17:00 20200101</span>
                <h3 class="rep-list-title">Zemsta nietoperza</h3>
                <a href="https://bilety.opera.wroclaw.pl/rezerwacja/?id=456">Kup bilet</a>
            </div>
        </body>
        </html>
        """

        scraper = OperaWroclawScraper(opera_wroclaw_house, config)

        with aioresponses() as mocked:
            mocked.get(opera_wroclaw_house.repertoire_url, body=html)
            result = await scraper.scrape()

        assert result.success is True
        # Should only find Halka (Zemsta nietoperza has past date and wrong opera)
        assert len(result.performances) == 1
        assert result.performances[0].opera_name == "Halka"
        assert result.performances[0].date.year == test_date.year
        assert result.performances[0].date.month == test_date.month
        assert result.performances[0].date.day == test_date.day

    @pytest.mark.asyncio
    async def test_ignores_entries_without_date(self, opera_wroclaw_house, config):
        """Test that entries without YYYYMMDD date are ignored"""
        html = """
        <html>
        <body>
            <div class="sidebar">
                <h3>Halka</h3>
                <p>Informacje o spektaklu</p>
            </div>
        </body>
        </html>
        """

        scraper = OperaWroclawScraper(opera_wroclaw_house, config)

        with aioresponses() as mocked:
            mocked.get(opera_wroclaw_house.repertoire_url, body=html)
            result = await scraper.scrape()

        assert result.success is True
        assert len(result.performances) == 0


class TestOperaBaltyckaGdanskScraper:
    """Tests for Opera Bałtycka Gdańsk scraper"""

    @pytest.mark.asyncio
    async def test_parses_polish_date_format(self, opera_baltycka_house, config):
        """Test parsing Polish date format like '31 stycznia 2026'"""
        test_date = future_date(30)
        polish_date = format_date_polish(test_date)

        html = f"""
        <html>
        <body>
            <div class="event">
                <span>{polish_date}</span>
                <h3>Straszny Dwór</h3>
                <a href="/bilety">Kup bilet</a>
            </div>
        </body>
        </html>
        """

        scraper = OperaBaltyckaGdanskScraper(opera_baltycka_house, config)

        with aioresponses() as mocked:
            mocked.get(opera_baltycka_house.repertoire_url, body=html)
            result = await scraper.scrape()

        assert result.success is True
        assert len(result.performances) == 1
        perf = result.performances[0]
        assert perf.opera_name == "Straszny Dwór"
        assert perf.date.year == test_date.year
        assert perf.date.month == test_date.month
        assert perf.date.day == test_date.day
        assert perf.time == "19:00"


class TestGenericScraper:
    """Tests for generic scraper"""

    @pytest.mark.asyncio
    async def test_detects_target_opera_case_insensitive(self, config):
        """Test that opera matching is case insensitive"""
        house = OperaHouse(
            name="Test Opera",
            city="Test City",
            base_url="https://example.com",
            repertoire_url="https://example.com/repertuar",
        )

        test_date = future_date(60)

        html = f"""
        <html>
        <body>
            <article class="event">
                <h3>HALKA - premiera</h3>
                <span class="date">{test_date.strftime('%d.%m.%Y')}</span>
                <a href="/bilety">Kup bilet</a>
            </article>
        </body>
        </html>
        """

        scraper = GenericOperaScraper(house, config)

        with aioresponses() as mocked:
            mocked.get(house.repertoire_url, body=html)
            result = await scraper.scrape()

        assert result.success is True
        # Should find Halka despite uppercase
        halka_found = any(p.opera_name == "Halka" for p in result.performances)
        assert halka_found


class TestScraperErrorHandling:
    """Tests for error handling in scrapers"""

    @pytest.mark.asyncio
    async def test_handles_network_error_gracefully(self, teatr_wielki_house, config):
        """Test that network errors are handled gracefully"""
        scraper = TeatrWielkiWarszawaScraper(teatr_wielki_house, config)

        with aioresponses() as mocked:
            # Simulate network error
            mocked.get("https://teatrwielki.pl/kalendarium/", exception=Exception("Network error"))
            for i in range(7):
                target_date = datetime.now()
                year = target_date.year + (i // 12)
                month = ((target_date.month + i - 1) % 12) + 1
                mocked.get(
                    f"https://teatrwielki.pl/kalendarium/data/{year}/{month:02d}/",
                    exception=Exception("Network error"),
                )

            result = await scraper.scrape()

        # Should return empty results, not crash
        assert result.success is True
        assert len(result.performances) == 0

    @pytest.mark.asyncio
    async def test_handles_malformed_html(self, opera_wroclaw_house, config):
        """Test that malformed HTML is handled gracefully"""
        html = "<html><body><div class='broken"  # Malformed HTML

        scraper = OperaWroclawScraper(opera_wroclaw_house, config)

        with aioresponses() as mocked:
            mocked.get(opera_wroclaw_house.repertoire_url, body=html)
            result = await scraper.scrape()

        # Should not crash
        assert result.success is True
