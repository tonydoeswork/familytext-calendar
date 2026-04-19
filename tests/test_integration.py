"""
Single end-to-end integration test: full router path with all external APIs mocked
at the service boundary.
"""
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

_ENV = {
    'TWILIO_ACCOUNT_SID': 'ACtest',
    'TWILIO_AUTH_TOKEN':  'authtoken',
    'TWILIO_PHONE_NUMBER': '+15550000000',
    'ANTHROPIC_API_KEY':  'sk-test',
    'GOOGLE_CALENDAR_ID': 'cal@test.com',
    'GOOGLE_CREDENTIALS_JSON': '{"installed":{"client_id":"x","client_secret":"y","token_uri":"z"}}',
    'GOOGLE_TOKEN_JSON': '{"token":"t","refresh_token":"r","token_uri":"z","client_id":"x","client_secret":"y","scopes":["https://www.googleapis.com/auth/calendar"]}',
    'REGISTERED_USERS': '[{"phone":"+15551234567","name":"Tony"}]',
    'SUMMARY_RECIPIENTS': '+15551234567',
    'SUMMARY_TIME': '07:30',
    'TZ': 'America/Chicago',
    'PUBLIC_BASE_URL': 'https://test.up.railway.app',
    'WEBHOOK_SECRET': 'authtoken',
    'LOG_LEVEL': 'WARNING',
}

TONY_PHONE = '+15551234567'


@pytest.fixture(autouse=True)
def mock_env(monkeypatch):
    for k, v in _ENV.items():
        monkeypatch.setenv(k, v)


def test_high_confidence_add_end_to_end():
    """
    POST /webhook/twilio with a valid, high-confidence add message.
    Asserts: calendar.create_event called once with correct ParsedEvent,
             send_sms called once with confirmation, HTTP 200 returned.
    """
    from app.models.event import ParsedEvent
    from app.models.intent import Intent

    parsed = ParsedEvent(
        title='Dentist', date='2026-04-24', time='14:00',
        duration_minutes=60, location='Downtown',
        confidence='high', missing_fields=[], ambiguous_fields=[],
        raw_message='dentist thursday 2pm downtown',
    )

    with (
        patch('app.services.calendar.init_calendar_service'),
        patch('app.services.session.init_session_store'),
        patch('app.scheduler.start_scheduler'),
        patch('app.scheduler.stop_scheduler'),
        patch('app.router._validate_twilio_signature', return_value=True),
        patch('app.router.classify_intent', return_value=Intent.ADD),
        patch('app.router.parse_event', return_value=parsed),
        patch('app.router.cal.create_event', return_value='event-id-123') as mock_create,
        patch('app.router.send_sms') as mock_sms,
    ):
        from app.main import app
        with TestClient(app) as client:
            resp = client.post(
                '/webhook/twilio',
                data={'From': TONY_PHONE, 'Body': 'dentist thursday 2pm downtown'},
            )

    assert resp.status_code == 200
    mock_create.assert_called_once()
    created_event: ParsedEvent = mock_create.call_args[0][0]
    assert created_event.title == 'Dentist'
    assert created_event.date == '2026-04-24'
    assert created_event.time == '14:00'

    mock_sms.assert_called_once()
    confirmation_body = mock_sms.call_args[0][1]
    assert 'Added' in confirmation_body
    assert 'Dentist' in confirmation_body
