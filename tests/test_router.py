from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

# Patch all external services before importing the app
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
UNKNOWN_PHONE = '+15559999999'
WEBHOOK_URL = '/webhook/twilio'


def _form(phone: str, body: str) -> dict:
    return {'From': phone, 'Body': body}


@pytest.fixture(autouse=True)
def mock_env(monkeypatch):
    for k, v in _ENV.items():
        monkeypatch.setenv(k, v)


@pytest.fixture
def client():
    with (
        patch('app.services.calendar.init_calendar_service'),
        patch('app.services.session.init_session_store'),
        patch('app.scheduler.start_scheduler'),
        patch('app.scheduler.stop_scheduler'),
        patch('app.router._validate_twilio_signature', return_value=True),
    ):
        from app.main import app
        with TestClient(app) as c:
            yield c


def test_invalid_signature_returns_403(client):
    with patch('app.router._validate_twilio_signature', return_value=False):
        resp = client.post(WEBHOOK_URL, data=_form(TONY_PHONE, 'hi'))
    assert resp.status_code == 403


@patch('app.router.send_sms')
def test_unregistered_number_returns_200_with_rejection(mock_sms, client):
    resp = client.post(WEBHOOK_URL, data=_form(UNKNOWN_PHONE, 'dentist thursday 2pm'))
    assert resp.status_code == 200
    mock_sms.assert_called_once()
    assert "isn't registered" in mock_sms.call_args[0][1]


@patch('app.router.send_sms')
@patch('app.router.classify_intent')
@patch('app.router.parse_event')
@patch('app.router.cal.create_event')
def test_high_confidence_add_creates_event_and_confirms(
    mock_create, mock_parse, mock_classify, mock_sms, client
):
    from app.models.event import ParsedEvent
    from app.models.intent import Intent

    mock_classify.return_value = Intent.ADD
    mock_parse.return_value = ParsedEvent(
        title='Dentist', date='2026-04-24', time='14:00',
        confidence='high', missing_fields=[], ambiguous_fields=[],
        raw_message='dentist thursday 2pm',
    )

    resp = client.post(WEBHOOK_URL, data=_form(TONY_PHONE, 'dentist thursday 2pm'))
    assert resp.status_code == 200
    mock_create.assert_called_once()
    mock_sms.assert_called_once()
    assert 'Added' in mock_sms.call_args[0][1]


@patch('app.router.send_sms')
@patch('app.router.classify_intent')
@patch('app.router.parse_event')
@patch('app.router.get_session')
def test_mid_clarification_routes_to_handler(
    mock_get_session, mock_parse, mock_classify, mock_sms, client
):
    from datetime import datetime, timezone
    from app.models.event import ParsedEvent, PendingSession
    from app.models.intent import Intent

    existing_session = PendingSession(
        phone=TONY_PHONE, flow_type='clarify',
        partial_event=ParsedEvent(
            title='Pediatrician', date='2026-04-22', time='',
            confidence='low', missing_fields=['time'], ambiguous_fields=[],
            raw_message='pediatrician tuesday',
        ),
        created_at=datetime.now(timezone.utc), prompt_sent='What time?',
    )
    mock_get_session.return_value = existing_session
    mock_classify.return_value = Intent.ADD
    mock_parse.return_value = ParsedEvent(
        title='Pediatrician', date='2026-04-22', time='10:00',
        confidence='high', missing_fields=[], ambiguous_fields=[],
        raw_message='pediatrician tuesday 10am',
    )

    with patch('app.router.cal.create_event'), patch('app.router.clear_session'):
        resp = client.post(WEBHOOK_URL, data=_form(TONY_PHONE, '10am'))
    assert resp.status_code == 200


@patch('app.router.send_sms')
@patch('app.router.classify_intent')
def test_confirm_yes_with_no_session(mock_classify, mock_sms, client):
    from app.models.intent import Intent
    from app.services import session as sess_mod
    sess_mod._sessions.clear()
    mock_classify.return_value = Intent.CONFIRM_YES
    resp = client.post(WEBHOOK_URL, data=_form(TONY_PHONE, 'YES'))
    assert resp.status_code == 200
    assert 'Nothing waiting' in mock_sms.call_args[0][1]


@patch('app.router.send_sms')
@patch('app.router.classify_intent')
@patch('app.router.get_session')
@patch('app.router.clear_session')
def test_confirm_no_clears_session(mock_clear, mock_get_session, mock_classify, mock_sms, client):
    from datetime import datetime, timezone
    from app.models.event import ParsedEvent, PendingSession
    from app.models.intent import Intent

    s = PendingSession(
        phone=TONY_PHONE, flow_type='confirm',
        partial_event=ParsedEvent(
            title='Dentist', date='2026-04-24', time='14:00',
            confidence='medium', missing_fields=[], ambiguous_fields=['date'],
            raw_message='dentist tuesday',
        ),
        created_at=datetime.now(timezone.utc), prompt_sent='Confirm?',
    )
    mock_get_session.return_value = s
    mock_classify.return_value = Intent.CONFIRM_NO

    resp = client.post(WEBHOOK_URL, data=_form(TONY_PHONE, 'NO'))
    assert resp.status_code == 200
    mock_clear.assert_called_once_with(TONY_PHONE)
    assert 'Cancelled' in mock_sms.call_args[0][1]


def test_health_returns_200(client):
    resp = client.get('/health')
    assert resp.status_code == 200
    assert resp.json()['status'] == 'ok'


@patch('app.router.send_sms')
@patch('app.router.classify_intent')
@patch('app.router.parse_event')
def test_three_failed_clarifications_trigger_giveup(mock_parse, mock_classify, mock_sms, client):
    from datetime import datetime, timezone
    from app.models.event import ParsedEvent, PendingSession
    from app.models.intent import Intent
    from app.services import session as sess_mod

    sess_mod._sessions.clear()
    s = PendingSession(
        phone=TONY_PHONE, flow_type='clarify',
        partial_event=ParsedEvent(
            title='Dentist', date='2026-04-24', time='',
            confidence='low', missing_fields=['time'], ambiguous_fields=[],
            raw_message='dentist thursday',
        ),
        created_at=datetime.now(timezone.utc), prompt_sent='What time?',
        clarify_attempts=2,
    )
    sess_mod._sessions[TONY_PHONE] = s
    mock_classify.return_value = Intent.UNKNOWN
    mock_parse.return_value = ParsedEvent(
        title='Dentist', date='2026-04-24', time='',
        confidence='low', missing_fields=['time'], ambiguous_fields=[],
        raw_message='dentist thursday whenever',
    )

    resp = client.post(WEBHOOK_URL, data=_form(TONY_PHONE, 'whenever'))
    assert resp.status_code == 200
    last_msg = mock_sms.call_args[0][1]
    assert 'trouble' in last_msg or 'start over' in last_msg
    assert sess_mod.get_session(TONY_PHONE) is None
