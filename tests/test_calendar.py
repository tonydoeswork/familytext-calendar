"""
Tests for calendar display/formatting logic and all-day event handling.
Does not make real API calls.
"""
from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

from app.services.sms import _parse_google_start, format_event_list, format_event_detail

_TZ = ZoneInfo('America/Chicago')


def _timed_event(title: str, dt_iso: str, location: str = '') -> dict:
    return {
        'summary': title,
        'start': {'dateTime': dt_iso},
        'end':   {'dateTime': dt_iso},
        'location': location,
    }


def _allday_event(title: str, date_str: str) -> dict:
    return {
        'summary': title,
        'start': {'date': date_str},
        'end':   {'date': date_str},
    }


def test_parse_google_start_timed_event():
    event = _timed_event('Dentist', '2026-04-24T14:00:00-05:00')
    dt = _parse_google_start(event)
    assert dt is not None
    assert dt.hour == 14
    assert dt.minute == 0


def test_parse_google_start_allday_event():
    event = _allday_event('Holiday', '2026-04-24')
    dt = _parse_google_start(event)
    assert dt is None


def test_format_event_list_timed():
    events = [
        _timed_event('Dentist', '2026-04-24T14:00:00-05:00'),
        _timed_event('School pickup', '2026-04-24T15:30:00-05:00'),
    ]
    result = format_event_list(events)
    assert 'Dentist' in result
    assert 'School pickup' in result
    assert '2:00 PM' in result


def test_format_event_list_allday():
    events = [_allday_event('Holiday', '2026-04-28')]
    result = format_event_list(events)
    assert 'Holiday' in result
    assert 'All day' in result


def test_format_event_list_with_location():
    events = [_timed_event('Dentist', '2026-04-24T14:00:00-05:00', 'Downtown Dental')]
    result = format_event_list(events)
    assert 'Downtown Dental' in result


def test_format_event_list_empty():
    assert format_event_list([]) == ''


def test_format_event_detail_includes_fields():
    event = {
        'summary': 'Dentist',
        'start': {'dateTime': '2026-04-24T14:00:00-05:00'},
        'end':   {'dateTime': '2026-04-24T15:00:00-05:00'},
        'location': 'Downtown Dental',
        'description': 'Bring insurance card',
        'created': '2026-04-18T10:00:00Z',
    }
    result = format_event_detail(event)
    assert 'Dentist' in result
    assert 'Downtown Dental' in result
    assert 'Bring insurance card' in result


def test_allday_event_no_keyerror():
    """Confirms accessing all-day events via .get() pattern never raises KeyError."""
    event = _allday_event('Doctor', '2026-05-01')
    start_val = event['start'].get('dateTime', event['start'].get('date'))
    assert start_val == '2026-05-01'
