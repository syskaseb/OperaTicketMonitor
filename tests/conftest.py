"""Pytest configuration and fixtures"""
import pytest
from config import MonitorConfig


@pytest.fixture
def fast_config():
    """Config with reduced timeouts for faster tests"""
    config = MonitorConfig()
    config.max_retries = 1
    config.retry_delay_seconds = 0
    config.request_timeout_seconds = 5
    return config
