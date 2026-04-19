from datetime import datetime
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

import pytest

from app.models.event import ParsedEvent
from app.services.sms import (
    format_confirmation_prompt,
    format_daily_summary,
    format_event_list,
    format_week_summary,
    send_sms,
)

_TZ = ZoneInfo('America/Chicago')


def _make_google_event(title: str, date_str: str, time_str: str, location: str = '') -> dict:
    return {
        'summary': title,
        'start': {'dateTime': f'{date_str}T{time_str}:00-05:00'},
        'end':   {'dateTime': f'{date_str}T{time_str}:00-05:00'},
        'location': location,
    }


def test_format_daily_summary_empty():
    now = datetime(2026, 4, 28, 7, 30, tzinfo=_TZ)
    result = format_daily_summary(now, [])
    assert 'Nothing on the calendar' in result


def test_format_daily_summary_with_events():
    now = datetime(2026, 4, 28, 7, 30, tzinfo=_TZ)
    events = [
        _make_google_event('Dentist', '2026-04-28', '14:00'),
        _make_google_event('School pickup', '2026-04-28', '15:30'),
    ]
    result = format_daily_summary(now, events)
    assert 'Tuesday' in result or 'Monday' in result or 'Apr' in result
    assert 'Dentist' in result
    assert 'School pickup' in result


def test_format_week_summary():
    from datetime import date
    week = {
        date(2026, 4, 27): [],
        date(2026, 4, 28): [_make_google_event('X', '2026-04-28', '10:00'),
                            _make_google_event('Y', '2026-04-28', '14:00')],
        date(2026, 4, 29): [_make_google_event('Z', '2026-04-29', '09:00')],
        date(2026, 4, 30): [],
        date(2026, 5, 1):  [],
        date(2026, 5, 2):  [],
        date(2026, 5, 3):  [],
    }
    result = format_week_summary(week)
    assert '2 events' in result
    assert '1 event' in result
    assert 'none' in result
    assert 'Reply with a day' in result


@patch.dict('os.environ', {'TWILIO_PHONE_NUMBER': '+15550000000', 'TWILIO_ACCOUNT_SID': 'x', 'TWILIO_AUTH_TOKEN': 'y'})
@patch('app.services.sms._get_client')
def test_send_sms_exact_1600_chars(mock_client):
    body = 'x' * 1600
    send_sms('+15550001111', body)
    actual_body = mock_client.return_value.messages.create.call_args[1]['body']
    assert len(actual_body) == 1600


@patch.dict('os.environ', {'TWILIO_PHONE_NUMBER': '+15550000000', 'TWILIO_ACCOUNT_SID': 'x', 'TWILIO_AUTH_TOKEN': 'y'})
@patch('app.services.sms._get_client')
def test_send_sms_truncates_at_1601(mock_client):
    body = 'x' * 1601
    send_sms('+15550001111', body)
    actual_body = mock_client.return_value.messages.create.call_args[1]['body']
    assert len(actual_body) == 1600


def test_format_confirmation_prompt_contains_event_info():
    event = ParsedEvent(
        title='Pediatrician', date='2026-04-22', time='10:00',
        raw_message='pediatrician tuesday 10am',
    )
    result = format_confirmation_prompt(event)
    assert 'Pediatrician' in result
    assert 'YES' in result
    assert 'NO' in result
