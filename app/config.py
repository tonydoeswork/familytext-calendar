import json
import logging
import os
from dataclasses import dataclass

logger = logging.getLogger(__name__)

_REQUIRED_VARS = [
    'TWILIO_ACCOUNT_SID',
    'TWILIO_AUTH_TOKEN',
    'TWILIO_PHONE_NUMBER',
    'ANTHROPIC_API_KEY',
    'GOOGLE_CALENDAR_ID',
    'GOOGLE_CREDENTIALS_JSON',
    'GOOGLE_TOKEN_JSON',
    'REGISTERED_USERS',
    'SUMMARY_RECIPIENTS',
    'SUMMARY_TIME',
    'TZ',
    'PUBLIC_BASE_URL',
    'WEBHOOK_SECRET',
]


@dataclass
class RegisteredUser:
    phone: str
    name: str


def validate_config() -> None:
    missing = [v for v in _REQUIRED_VARS if not os.environ.get(v)]
    if missing:
        raise ValueError(f"Missing required environment variables: {', '.join(missing)}")
    logger.info('Config validated — all required vars present')


def get_registered_users() -> list[RegisteredUser]:
    raw = os.environ.get('REGISTERED_USERS', '[]')
    return [RegisteredUser(phone=u['phone'], name=u['name']) for u in json.loads(raw)]


def get_registered_user(phone: str) -> RegisteredUser | None:
    return next((u for u in get_registered_users() if u.phone == phone), None)


def get_summary_recipients() -> list[str]:
    raw = os.environ.get('SUMMARY_RECIPIENTS', '')
    return [p.strip() for p in raw.split(',') if p.strip()]


def get_summary_time() -> tuple[int, int]:
    raw = os.environ.get('SUMMARY_TIME', '07:30')
    h, m = raw.split(':')
    return int(h), int(m)
