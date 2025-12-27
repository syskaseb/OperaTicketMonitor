"""Unit tests for helper functions in scrapers.py"""
import pytest
from datetime import datetime

from scrapers import (
    format_polish_date,
    is_future_date,
    is_available,
    POLISH_MONTHS,
    POLISH_WEEKDAYS,
)
from models import TicketStatus


class TestFormatPolishDate:
    """Tests for format_polish_date function"""

    def test_formats_date_correctly(self):
        # Wednesday, January 15, 2025
        dt = datetime(2025, 1, 15)
        result = format_polish_date(dt)
        assert result == "Środa 15 stycznia 2025"

    def test_formats_weekend_date(self):
        # Saturday, May 10, 2025
        dt = datetime(2025, 5, 10)
        result = format_polish_date(dt)
        assert result == "Sobota 10 maja 2025"

    def test_formats_sunday(self):
        # Sunday, December 7, 2025
        dt = datetime(2025, 12, 7)
        result = format_polish_date(dt)
        assert result == "Niedziela 7 grudnia 2025"

    def test_all_months_have_polish_names(self):
        """Ensure all 12 months have Polish translations"""
        assert len(POLISH_MONTHS) == 12
        for month in range(1, 13):
            assert month in POLISH_MONTHS
            assert isinstance(POLISH_MONTHS[month], str)

    def test_all_weekdays_have_polish_names(self):
        """Ensure all 7 weekdays have Polish translations"""
        assert len(POLISH_WEEKDAYS) == 7
        for day in range(7):
            assert day in POLISH_WEEKDAYS
            assert isinstance(POLISH_WEEKDAYS[day], str)


class TestIsFutureDate:
    """Tests for is_future_date function"""

    def test_future_date_returns_true(self):
        future = datetime(2030, 6, 15)
        assert is_future_date(future) is True

    def test_past_date_returns_false(self):
        past = datetime(2020, 1, 1)
        assert is_future_date(past) is False

    def test_none_returns_false(self):
        assert is_future_date(None) is False

    def test_today_returns_true(self):
        today = datetime.now().replace(hour=12, minute=0, second=0, microsecond=0)
        assert is_future_date(today) is True


class TestIsAvailable:
    """Tests for is_available function"""

    def test_available_returns_true(self):
        assert is_available(TicketStatus.AVAILABLE) is True

    def test_limited_returns_true(self):
        assert is_available(TicketStatus.LIMITED) is True

    def test_sold_out_returns_false(self):
        assert is_available(TicketStatus.SOLD_OUT) is False

    def test_unknown_returns_false(self):
        assert is_available(TicketStatus.UNKNOWN) is False
