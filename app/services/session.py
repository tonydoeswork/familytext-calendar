import json
import logging
import os
from datetime import datetime, timezone

from app.models.event import ParsedEvent, PendingSession

logger = logging.getLogger(__name__)

_SESSION_TTL_MINUTES = 15
_sessions: dict[str, PendingSession] = {}


# ── serialisation helpers ────────────────────────────────────────────────────

def _session_to_dict(s: PendingSession) -> dict:
    e = s.partial_event
    return {
        'phone': s.phone,
        'flow_type': s.flow_type,
        'partial_event': {
            'title': e.title,
            'date': e.date,
            'time': e.time,
            'duration_minutes': e.duration_minutes,
            'location': e.location,
            'confidence': e.confidence,
            'missing_fields': e.missing_fields,
            'ambiguous_fields': e.ambiguous_fields,
            'raw_message': e.raw_message,
        },
        'created_at': s.created_at.isoformat(),
        'prompt_sent': s.prompt_sent,
        'clarify_attempts': s.clarify_attempts,
    }


def _dict_to_session(d: dict) -> PendingSession:
    ed = d['partial_event']
    return PendingSession(
        phone=d['phone'],
        flow_type=d['flow_type'],
        partial_event=ParsedEvent(
            title=ed['title'],
            date=ed['date'],
            time=ed['time'],
            duration_minutes=ed.get('duration_minutes', 60),
            location=ed.get('location'),
            confidence=ed.get('confidence', 'low'),
            missing_fields=ed.get('missing_fields', []),
            ambiguous_fields=ed.get('ambiguous_fields', []),
            raw_message=ed.get('raw_message', ''),
        ),
        created_at=datetime.fromisoformat(d['created_at']),
        prompt_sent=d['prompt_sent'],
        clarify_attempts=d.get('clarify_attempts', 0),
    )


# ── file-backed store (dev only) ─────────────────────────────────────────────

def _session_file() -> str:
    return os.environ.get('SESSION_FILE_PATH', './session_store.json')


def _load_from_file() -> None:
    path = _session_file()
    if not os.path.exists(path):
        return
    try:
        with open(path, encoding='utf-8') as f:
            raw = json.load(f)
        for phone, d in raw.items():
            _sessions[phone] = _dict_to_session(d)
        logger.info(f"Loaded {len(_sessions)} sessions from {path}")
    except Exception as exc:
        logger.error(f"Failed to load session file: {exc}")


def _save_to_file() -> None:
    path = _session_file()
    try:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump({k: _session_to_dict(v) for k, v in _sessions.items()}, f, indent=2)
    except Exception as exc:
        logger.error(f"Failed to save session file: {exc}")


def _is_dev() -> bool:
    return os.environ.get('ENV') == 'development'


# ── public API ───────────────────────────────────────────────────────────────

def init_session_store() -> None:
    if _is_dev():
        _load_from_file()


def get_session(phone: str) -> PendingSession | None:
    session = _sessions.get(phone)
    if session is None:
        return None
    elapsed = (datetime.now(timezone.utc) - session.created_at).total_seconds() / 60
    if elapsed > _SESSION_TTL_MINUTES:
        return None  # expired; check_expired_sessions() will clean up and notify
    return session


def set_session(session: PendingSession) -> None:
    _sessions[session.phone] = session
    if _is_dev():
        _save_to_file()


def clear_session(phone: str) -> None:
    _sessions.pop(phone, None)
    if _is_dev():
        _save_to_file()


def check_expired_sessions() -> None:
    # Import here to avoid circular import (session ← sms ← session)
    from app.services.sms import send_sms

    now = datetime.now(timezone.utc)
    expired = [
        phone for phone, s in list(_sessions.items())
        if (now - s.created_at).total_seconds() / 60 > _SESSION_TTL_MINUTES
    ]
    for phone in expired:
        send_sms(phone, 'Your pending event timed out. Please resend your message to try again.')
        del _sessions[phone]
        logger.info(f"Expired session cleared phone={phone}")
    if _is_dev() and expired:
        _save_to_file()
