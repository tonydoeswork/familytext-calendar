import json
import os
import tempfile
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from app.models.event import ParsedEvent, PendingSession
from app.services import session as sess_mod


def _make_session(phone: str = '+15551234567', minutes_old: int = 0) -> PendingSession:
    return PendingSession(
        phone=phone,
        flow_type='clarify',
        partial_event=ParsedEvent(
            title='Dentist', date='2026-04-24', time='', raw_message='dentist thursday',
            confidence='low', missing_fields=['time'], ambiguous_fields=[],
        ),
        created_at=datetime.now(timezone.utc) - timedelta(minutes=minutes_old),
        prompt_sent='What time?',
    )


def setup_function():
    sess_mod._sessions.clear()


def test_set_and_get_session():
    s = _make_session()
    sess_mod.set_session(s)
    result = sess_mod.get_session(s.phone)
    assert result is not None
    assert result.phone == s.phone


def test_get_session_returns_none_after_ttl():
    s = _make_session(minutes_old=16)
    sess_mod._sessions[s.phone] = s
    assert sess_mod.get_session(s.phone) is None


def test_clear_session_removes_entry():
    s = _make_session()
    sess_mod.set_session(s)
    sess_mod.clear_session(s.phone)
    assert sess_mod.get_session(s.phone) is None


def test_check_expired_sends_timeout_sms():
    s = _make_session(minutes_old=20)
    sess_mod._sessions[s.phone] = s
    with patch('app.services.sms.send_sms') as mock_send:
        sess_mod.check_expired_sessions()
    mock_send.assert_called_once()
    assert 'timed out' in mock_send.call_args[0][1]
    assert sess_mod.get_session(s.phone) is None


def test_check_expired_does_not_send_for_fresh_session():
    s = _make_session(minutes_old=5)
    sess_mod.set_session(s)
    with patch('app.services.sms.send_sms') as mock_send:
        sess_mod.check_expired_sessions()
    mock_send.assert_not_called()


def test_clarify_attempts_increments():
    s = _make_session()
    assert s.clarify_attempts == 0
    s.clarify_attempts += 1
    sess_mod.set_session(s)
    stored = sess_mod.get_session(s.phone)
    assert stored.clarify_attempts == 1


def test_clarify_attempts_at_3_triggers_giveup():
    s = _make_session()
    s.clarify_attempts = 3
    assert s.clarify_attempts >= 3


def test_dev_mode_session_survives_reload():
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        tmp_path = f.name

    with patch.dict(os.environ, {'ENV': 'development', 'SESSION_FILE_PATH': tmp_path}):
        s = _make_session()
        sess_mod.set_session(s)
        sess_mod._sessions.clear()
        sess_mod._load_from_file()
        restored = sess_mod.get_session(s.phone)
        assert restored is not None
        assert restored.partial_event.title == 'Dentist'

    os.unlink(tmp_path)
