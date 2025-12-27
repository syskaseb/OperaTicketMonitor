"""Integration tests for scrapers with mocked HTTP responses"""
import pytest
from datetime import datetime
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
        html = """
        <html>
        <body>
            <ul>
                <li class="data-event">
                    <h3><a href="/kalendarium/2025-2026/halka/termin/2026-05-07_19-00/">Halka</a></h3>
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
        assert halka.date.year == 2026
        assert halka.date.month == 5
        assert halka.date.day == 7

    @pytest.mark.asyncio
    async def test_filters_sold_out_performances(self, teatr_wielki_house, config):
        """Test that sold out performances are filtered"""
        html = """
        <html>
        <body>
            <ul>
                <li class="data-event">
                    <h3><a href="/kalendarium/2025-2026/halka/termin/2026-05-07_19-00/">Halka</a></h3>
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
        html = """
        <html>
        <body>
            <div class="rep-single list">
                <span>7 maja, Cz 19:00 20260507</span>
                <h3 class="rep-list-title">Halka</h3>
                <a href="https://bilety.opera.wroclaw.pl/rezerwacja/?id=123">Kup bilet</a>
            </div>
            <div class="rep-single list">
                <span>31 grudnia, Śr 17:00 20251231</span>
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
        # Should only find Halka, not Zemsta nietoperza
        assert len(result.performances) == 1
        assert result.performances[0].opera_name == "Halka"
        assert result.performances[0].date.year == 2026
        assert result.performances[0].date.month == 5
        assert result.performances[0].date.day == 7

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
        """Test parsing Polish date format like '31 grudnia 2025'"""
        html = """
        <html>
        <body>
            <div class="event">
                <span>31 grudnia 2025 środa godz. 19:00</span>
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
        assert perf.date.year == 2025
        assert perf.date.month == 12
        assert perf.date.day == 31
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

        html = """
        <html>
        <body>
            <article class="event">
                <h3>HALKA - premiera</h3>
                <span class="date">15.06.2026</span>
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
