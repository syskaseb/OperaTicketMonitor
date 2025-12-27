"""
Data models for Opera Ticket Monitor
"""
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional
import json


class TicketStatus(Enum):
    """Ticket availability status"""
    AVAILABLE = "available"
    LIMITED = "limited"  # Few tickets left
    SOLD_OUT = "sold_out"
    UNKNOWN = "unknown"


@dataclass
class Performance:
    """Represents a single performance/show"""
    opera_name: str
    opera_house: str
    city: str
    date: Optional[datetime] = None
    date_str: str = ""  # Raw date string from website
    time: str = ""
    ticket_url: str = ""
    status: TicketStatus = TicketStatus.UNKNOWN
    price_range: str = ""
    venue: str = ""  # Specific venue/stage if applicable
    additional_info: str = ""

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization"""
        return {
            "opera_name": self.opera_name,
            "opera_house": self.opera_house,
            "city": self.city,
            "date": self.date.isoformat() if self.date else None,
            "date_str": self.date_str,
            "time": self.time,
            "ticket_url": self.ticket_url,
            "status": self.status.value,
            "price_range": self.price_range,
            "venue": self.venue,
            "additional_info": self.additional_info,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Performance":
        """Create from dictionary"""
        date = None
        if data.get("date"):
            try:
                date = datetime.fromisoformat(data["date"])
            except (ValueError, TypeError):
                pass

        return cls(
            opera_name=data.get("opera_name", ""),
            opera_house=data.get("opera_house", ""),
            city=data.get("city", ""),
            date=date,
            date_str=data.get("date_str", ""),
            time=data.get("time", ""),
            ticket_url=data.get("ticket_url", ""),
            status=TicketStatus(data.get("status", "unknown")),
            price_range=data.get("price_range", ""),
            venue=data.get("venue", ""),
            additional_info=data.get("additional_info", ""),
        )

    def unique_id(self) -> str:
        """Generate unique identifier for this performance"""
        return f"{self.opera_house}|{self.opera_name}|{self.date_str}|{self.time}"

    def __hash__(self):
        return hash(self.unique_id())

    def __eq__(self, other):
        if not isinstance(other, Performance):
            return False
        return self.unique_id() == other.unique_id()


@dataclass
class ScrapeResult:
    """Result of scraping an opera house website"""
    opera_house: str
    city: str
    success: bool
    performances: list[Performance] = field(default_factory=list)
    error_message: str = ""
    scrape_time: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict:
        return {
            "opera_house": self.opera_house,
            "city": self.city,
            "success": self.success,
            "performances": [p.to_dict() for p in self.performances],
            "error_message": self.error_message,
            "scrape_time": self.scrape_time.isoformat(),
        }


@dataclass
class MonitorState:
    """Persistent state for the monitor"""
    # Performances we've already notified about (to avoid spam)
    notified_performances: set[str] = field(default_factory=set)
    # Last check time for each opera house
    last_check_times: dict[str, datetime] = field(default_factory=dict)
    # Last successful scrape results
    last_results: dict[str, ScrapeResult] = field(default_factory=dict)

    def save(self, filepath: str) -> None:
        """Save state to file"""
        data = {
            "notified_performances": list(self.notified_performances),
            "last_check_times": {
                k: v.isoformat() for k, v in self.last_check_times.items()
            },
        }
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    @classmethod
    def load(cls, filepath: str) -> "MonitorState":
        """Load state from file"""
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
            return cls(
                notified_performances=set(data.get("notified_performances", [])),
                last_check_times={
                    k: datetime.fromisoformat(v)
                    for k, v in data.get("last_check_times", {}).items()
                },
            )
        except (FileNotFoundError, json.JSONDecodeError):
            return cls()

    def should_notify(self, performance: Performance) -> bool:
        """Check if we should notify about this performance"""
        return performance.unique_id() not in self.notified_performances

    def mark_notified(self, performance: Performance) -> None:
        """Mark a performance as already notified"""
        self.notified_performances.add(performance.unique_id())
