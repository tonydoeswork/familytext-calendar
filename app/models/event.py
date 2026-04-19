from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal


@dataclass
class ParsedEvent:
    title: str
    date: str                          # ISO 8601: YYYY-MM-DD
    time: str                          # 24h: HH:MM
    duration_minutes: int = 60
    location: str | None = None
    confidence: Literal['high', 'medium', 'low'] = 'low'
    missing_fields: list[str] = field(default_factory=list)
    ambiguous_fields: list[str] = field(default_factory=list)
    raw_message: str = ''


@dataclass
class PendingSession:
    phone: str
    flow_type: Literal['clarify', 'confirm']
    partial_event: ParsedEvent
    created_at: datetime               # UTC
    prompt_sent: str
    clarify_attempts: int = 0
