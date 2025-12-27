"""
Configuration for Opera Ticket Monitor
"""
from dataclasses import dataclass, field
from typing import Optional
import os


@dataclass
class EmailConfig:
    """Email notification settings"""
    smtp_server: str = "smtp.gmail.com"
    smtp_port: int = 587
    sender_email: str = os.getenv("SENDER_EMAIL", "")
    sender_password: str = os.getenv("SENDER_PASSWORD", "")  # App password for Gmail
    recipient_emails: list[str] = field(default_factory=lambda: [
        e.strip() for e in os.getenv("RECIPIENT_EMAILS", "syska.seb@gmail.com,kingatoczko@gmail.com").split(",")
    ])


@dataclass
class MonitorConfig:
    """Monitor settings"""
    # Check every 15 minutes - good balance between:
    # - Not overwhelming servers (respect their resources)
    # - Catching tickets quickly (tickets can sell fast)
    # - AWS costs (fewer invocations = lower cost)
    check_interval_minutes: int = 15

    # Retry settings for failed requests
    max_retries: int = 3
    retry_delay_seconds: int = 30

    # Request timeout
    request_timeout_seconds: int = 30

    # User agent to avoid being blocked
    user_agent: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )


@dataclass
class OperaHouse:
    """Opera house configuration"""
    name: str
    city: str
    base_url: str
    repertoire_url: str
    tickets_url_pattern: Optional[str] = None
    enabled: bool = True


# All major Polish opera houses
OPERA_HOUSES: list[OperaHouse] = [
    OperaHouse(
        name="Teatr Wielki - Opera Narodowa",
        city="Warszawa",
        base_url="https://teatrwielki.pl",
        repertoire_url="https://teatrwielki.pl/repertuar/",
        tickets_url_pattern="https://teatrwielki.pl/bilety/"
    ),
    OperaHouse(
        name="Opera Krakowska",
        city="Kraków",
        base_url="https://opera.krakow.pl",
        repertoire_url="https://opera.krakow.pl/pl/repertuar",
        tickets_url_pattern="https://opera.krakow.pl/pl/bilety"
    ),
    OperaHouse(
        name="Opera Wrocławska",
        city="Wrocław",
        base_url="https://www.opera.wroclaw.pl",
        repertoire_url="https://www.opera.wroclaw.pl/1/repertuar.php",
        tickets_url_pattern="https://bilety.opera.wroclaw.pl/"
    ),
    OperaHouse(
        name="Opera Bałtycka",
        city="Gdańsk",
        base_url="https://operabaltycka.pl",
        repertoire_url="https://operabaltycka.pl/repertuar/",
        tickets_url_pattern="https://operabaltycka.pl/bilety/"
    ),
    OperaHouse(
        name="Opera Śląska",
        city="Bytom",
        base_url="https://opera-slaska.pl",
        repertoire_url="https://opera-slaska.pl/repertuar",
        tickets_url_pattern="https://opera-slaska.pl/bilety"
    ),
    OperaHouse(
        name="Opera Nova",
        city="Bydgoszcz",
        base_url="https://opera.bydgoszcz.pl",
        repertoire_url="https://opera.bydgoszcz.pl/repertuar.html",
        tickets_url_pattern="https://opera.bydgoszcz.pl/bilety.html"
    ),
    OperaHouse(
        name="Teatr Wielki",
        city="Łódź",
        base_url="https://operalodz.com",
        repertoire_url="https://operalodz.com/Kalendarz,234",
        tickets_url_pattern="https://operalodz.com/bilety"
    ),
    OperaHouse(
        name="Teatr Wielki im. Stanisława Moniuszki",
        city="Poznań",
        base_url="https://opera.poznan.pl",
        repertoire_url="https://opera.poznan.pl/pl/repertuar",
        tickets_url_pattern="https://opera.poznan.pl/pl/bilety"
    ),
    OperaHouse(
        name="Opera i Filharmonia Podlaska",
        city="Białystok",
        base_url="https://oifp.eu",
        repertoire_url="https://oifp.eu/repertuar/",
        tickets_url_pattern="https://oifp.eu/bilety/"
    ),
]

# Operas we're looking for
TARGET_OPERAS: list[str] = [
    "Straszny Dwór",
    "Straszny dwór",
    "STRASZNY DWÓR",
    "Halka",
    "HALKA",
    "halka",
]

# Keywords for ticket availability
AVAILABILITY_KEYWORDS: list[str] = [
    "kup bilet",
    "bilety dostępne",
    "kup teraz",
    "rezerwuj",
    "dostępne",
    "wolne miejsca",
    "buy ticket",
    "available",
]

# Keywords indicating sold out
SOLD_OUT_KEYWORDS: list[str] = [
    "wyprzedane",
    "brak biletów",
    "sold out",
    "niedostępne",
    "brak miejsc",
]


@dataclass
class AppConfig:
    """Main application configuration"""
    email: EmailConfig = field(default_factory=EmailConfig)
    monitor: MonitorConfig = field(default_factory=MonitorConfig)
    opera_houses: list[OperaHouse] = field(default_factory=lambda: OPERA_HOUSES)
    target_operas: list[str] = field(default_factory=lambda: TARGET_OPERAS)

    # State file for tracking what we've already notified about
    state_file: str = "monitor_state.json"

    # Log file
    log_file: str = "opera_monitor.log"


def get_config() -> AppConfig:
    """Get application configuration"""
    return AppConfig()
