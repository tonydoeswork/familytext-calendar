from unittest.mock import MagicMock, patch

import pytest

from app.models.intent import Intent
from app.services.parser import classify_intent, parse_event


def _tool_use_block(data: dict):
    block = MagicMock()
    block.type = 'tool_use'
    block.input = data
    return block


def _mock_response(data: dict):
    resp = MagicMock()
    resp.content = [_tool_use_block(data)]
    return resp


@patch('app.services.parser._get_client')
def test_high_confidence_event(mock_get_client):
    mock_get_client.return_value.messages.create.return_value = _mock_response({
        'title': 'Dentist', 'date': '2026-04-24', 'time': '14:00',
        'duration_minutes': 60, 'location': None,
        'confidence': 'high', 'missing_fields': [], 'ambiguous_fields': [],
    })
    result = parse_event('dentist Thursday at 2pm', 'America/Chicago')
    assert result.title == 'Dentist'
    assert result.date == '2026-04-24'
    assert result.time == '14:00'
    assert result.missing_fields == []
    assert result.ambiguous_fields == []


@patch('app.services.parser._get_client')
def test_low_confidence_missing_time(mock_get_client):
    mock_get_client.return_value.messages.create.return_value = _mock_response({
        'title': 'Dentist', 'date': '2026-04-24', 'time': None,
        'duration_minutes': 60, 'location': None,
        'confidence': 'low', 'missing_fields': ['time'], 'ambiguous_fields': [],
    })
    result = parse_event('dentist thursday', 'America/Chicago')
    assert 'time' in result.missing_fields


@patch('app.services.parser._get_client')
def test_medium_confidence_ambiguous_date(mock_get_client):
    mock_get_client.return_value.messages.create.return_value = _mock_response({
        'title': 'Pediatrician', 'date': '2026-04-28', 'time': '10:00',
        'duration_minutes': 60, 'location': None,
        'confidence': 'medium', 'missing_fields': [], 'ambiguous_fields': ['date'],
    })
    result = parse_event('pediatrician tuesday', 'America/Chicago')
    assert 'date' in result.ambiguous_fields


@patch('app.services.parser._get_client')
def test_classify_intent_query_today(mock_get_client):
    mock_get_client.return_value.messages.create.return_value = _mock_response({'intent': 'query_today'})
    assert classify_intent("what's today", False) == Intent.QUERY_TODAY


@patch('app.services.parser._get_client')
def test_classify_intent_help(mock_get_client):
    for msg in ['HELP', '?']:
        mock_get_client.return_value.messages.create.return_value = _mock_response({'intent': 'help'})
        assert classify_intent(msg, False) == Intent.HELP


@patch('app.services.parser._get_client')
def test_classify_yes_with_pending_session(mock_get_client):
    mock_get_client.return_value.messages.create.return_value = _mock_response({'intent': 'confirm_yes'})
    assert classify_intent('YES', True) == Intent.CONFIRM_YES


@patch('app.services.parser._get_client')
def test_classify_yes_without_pending_session(mock_get_client):
    mock_get_client.return_value.messages.create.return_value = _mock_response({'intent': 'unknown'})
    assert classify_intent('YES', False) == Intent.UNKNOWN
