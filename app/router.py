import logging
import os
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Request
from fastapi.responses import Response

from app import config
from app.models.event import ParsedEvent, PendingSession
from app.models.intent import Intent
from app.services import calendar as cal
from app.services.parser import (
    classify_intent,
    extract_date_param,
    extract_detail_keyword,
    extract_search_params,
    parse_event,
)
from app.services.session import clear_session, get_session, set_session
from app.services.sms import (
    HELP_TEXT,
    format_clarification_prompt,
    format_confirmation_prompt,
    format_daily_summary,
    format_event_confirmation,
    format_event_detail,
    format_event_list,
    format_week_summary,
    send_sms,
)
from twilio.request_validator import RequestValidator

logger = logging.getLogger(__name__)
router = APIRouter()
_TZ = ZoneInfo('America/Chicago')

_UNRECOGNIZED = "Sorry, this number isn't registered. Ask Tony to add you."
_UNKNOWN_MSG = "I didn't understand that. Try 'dentist Tuesday 3pm' or 'what\u2019s tomorrow?'"
_CALENDAR_ERROR = "Couldn\u2019t reach Google Calendar \u2014 please try again."
_CANCELLED = 'Cancelled \u2014 event not added.'
_NOTHING_PENDING = 'Nothing waiting for confirmation. Try adding an event: dentist Thursday 2pm'
_GIVEUP = "I\u2019m having trouble understanding that. Please start over with a full message like \u2018dentist Tuesday 2pm.\u2019"
_MAX_CLARIFY = 3


def _twiml_200() -> Response:
    return Response(
        content='<?xml version="1.0" encoding="UTF-8"?><Response></Response>',
        media_type='application/xml',
        status_code=200,
    )


def _validate_twilio_signature(request: Request, form_dict: dict) -> bool:
    validator = RequestValidator(os.environ['WEBHOOK_SECRET'])
    url = os.environ['PUBLIC_BASE_URL'].rstrip('/') + '/webhook/twilio'
    signature = request.headers.get('X-Twilio-Signature', '')
    return validator.validate(url, form_dict, signature)


# ── event creation helper ────────────────────────────────────────────────────

def _create_and_confirm(phone: str, parsed: ParsedEvent) -> None:
    try:
        cal.create_event(parsed)
        send_sms(phone, format_event_confirmation(parsed))
    except Exception as exc:
        logger.error(f'create_event failed phone={phone}: {exc}')
        send_sms(phone, _CALENDAR_ERROR)


# ── ADD flow handlers ─────────────────────────────────────────────────────────

def _handle_add(phone: str, body: str) -> None:
    parsed = parse_event(body, 'America/Chicago')

    if parsed.missing_fields:
        prompt = format_clarification_prompt(parsed, parsed.missing_fields[0])
        set_session(PendingSession(
            phone=phone, flow_type='clarify', partial_event=parsed,
            created_at=datetime.now(timezone.utc), prompt_sent=prompt,
        ))
        send_sms(phone, prompt)
        return

    if parsed.ambiguous_fields:
        prompt = format_confirmation_prompt(parsed)
        set_session(PendingSession(
            phone=phone, flow_type='confirm', partial_event=parsed,
            created_at=datetime.now(timezone.utc), prompt_sent=prompt,
        ))
        send_sms(phone, prompt)
        return

    _create_and_confirm(phone, parsed)


def _handle_clarification_response(phone: str, body: str, session: PendingSession) -> None:
    combined = f'{session.partial_event.raw_message} {body}'
    parsed = parse_event(combined, 'America/Chicago')
    parsed.raw_message = combined

    if parsed.missing_fields:
        session.clarify_attempts += 1
        if session.clarify_attempts >= _MAX_CLARIFY:
            clear_session(phone)
            send_sms(phone, _GIVEUP)
            return
        prompt = format_clarification_prompt(parsed, parsed.missing_fields[0])
        session.partial_event = parsed
        session.prompt_sent = prompt
        set_session(session)
        send_sms(phone, prompt)
        return

    if parsed.ambiguous_fields:
        prompt = format_confirmation_prompt(parsed)
        session.flow_type = 'confirm'
        session.partial_event = parsed
        session.prompt_sent = prompt
        set_session(session)
        send_sms(phone, prompt)
        return

    clear_session(phone)
    _create_and_confirm(phone, parsed)


def _handle_confirmation(phone: str, session: PendingSession, intent: Intent) -> None:
    if intent == Intent.CONFIRM_NO:
        clear_session(phone)
        send_sms(phone, _CANCELLED)
        return

    # CONFIRM_YES
    if session.flow_type == 'confirm':
        clear_session(phone)
        _create_and_confirm(phone, session.partial_event)
        return

    # flow_type == 'clarify' — YES is not a valid clarification response
    session.clarify_attempts += 1
    if session.clarify_attempts >= _MAX_CLARIFY:
        clear_session(phone)
        send_sms(phone, _GIVEUP)
        return

    send_sms(phone, session.prompt_sent)
    set_session(session)


# ── query handlers ────────────────────────────────────────────────────────────

def _handle_query_today(phone: str) -> None:
    try:
        events = cal.get_events_for_date(date.today())
        send_sms(phone, format_daily_summary(datetime.now(_TZ), events))
    except Exception as exc:
        logger.error(f'query_today failed: {exc}')
        send_sms(phone, _CALENDAR_ERROR)


def _handle_query_date(phone: str, message: str) -> None:
    try:
        raw_date = extract_date_param(message)
        if raw_date:
            target = date.fromisoformat(raw_date)
        else:
            target = date.today()
        events = cal.get_events_for_date(target)
        if events:
            dt = datetime(target.year, target.month, target.day, tzinfo=_TZ)
            send_sms(phone, format_daily_summary(dt, events))
        else:
            send_sms(phone, 'Nothing on that day.')
    except Exception as exc:
        logger.error(f'query_date failed: {exc}')
        send_sms(phone, _CALENDAR_ERROR)


def _handle_query_week(phone: str) -> None:
    try:
        today = date.today()
        monday = today - __import__('datetime').timedelta(days=today.weekday())
        week = cal.get_events_for_week(monday)
        send_sms(phone, format_week_summary(week))
    except Exception as exc:
        logger.error(f'query_week failed: {exc}')
        send_sms(phone, _CALENDAR_ERROR)


def _handle_query_detail(phone: str, message: str) -> None:
    try:
        keyword = extract_detail_keyword(message)
        events = cal.get_event_detail(keyword)
        if not events:
            send_sms(phone, f'No upcoming events found for \u201c{keyword}\u201d.')
            return
        parts = [format_event_detail(e) for e in events]
        send_sms(phone, '\n\n'.join(parts))
    except Exception as exc:
        logger.error(f'query_detail failed: {exc}')
        send_sms(phone, _CALENDAR_ERROR)


def _handle_query_search(phone: str, message: str) -> None:
    try:
        params = extract_search_params(message)
        keyword = params['keyword']
        days = params.get('days', 90)
        events = cal.search_events(keyword, days)
        if not events:
            send_sms(phone, f'Nothing found for \u201c{keyword}\u201d in the next {days} days.')
            return
        count = len(events)
        header = f'Found {count} match{"es" if count != 1 else ""} for \u201c{keyword}\u201d (next {days} days):\n'
        send_sms(phone, header + format_event_list(events))
    except Exception as exc:
        logger.error(f'query_search failed: {exc}')
        send_sms(phone, _CALENDAR_ERROR)


# ── main webhook ──────────────────────────────────────────────────────────────

@router.post('/webhook/twilio')
async def twilio_webhook(request: Request) -> Response:
    form = await request.form()
    form_dict = dict(form)

    if not _validate_twilio_signature(request, form_dict):
        logger.warning(f'source_ip={request.client.host if request.client else "unknown"} reason=invalid_signature')
        return Response(status_code=403)

    phone = form_dict.get('From', '')
    body = (form_dict.get('Body') or '').strip()

    logger.info(f'phone={phone} message_length={len(body)} has_session={get_session(phone) is not None}')

    user = config.get_registered_user(phone)
    if user is None:
        send_sms(phone, _UNRECOGNIZED)
        return _twiml_200()

    session = get_session(phone)
    has_session = session is not None

    intent = classify_intent(body, has_session)
    logger.info(f'phone={phone} intent={intent.value}')

    if intent == Intent.HELP:
        send_sms(phone, HELP_TEXT)
        return _twiml_200()

    if intent in (Intent.CONFIRM_YES, Intent.CONFIRM_NO):
        if not has_session:
            send_sms(phone, _NOTHING_PENDING)
        else:
            _handle_confirmation(phone, session, intent)
        return _twiml_200()

    if intent == Intent.ADD:
        if has_session and session.flow_type == 'clarify':
            _handle_clarification_response(phone, body, session)
        else:
            _handle_add(phone, body)
        return _twiml_200()

    if intent == Intent.UNKNOWN:
        if has_session and session.flow_type == 'clarify':
            _handle_clarification_response(phone, body, session)
        else:
            send_sms(phone, _UNKNOWN_MSG)
        return _twiml_200()

    # Query intents
    if intent == Intent.QUERY_TODAY:
        _handle_query_today(phone)
    elif intent == Intent.QUERY_DATE:
        _handle_query_date(phone, body)
    elif intent == Intent.QUERY_WEEK:
        _handle_query_week(phone)
    elif intent == Intent.QUERY_DETAIL:
        _handle_query_detail(phone, body)
    elif intent == Intent.QUERY_SEARCH:
        _handle_query_search(phone, body)

    return _twiml_200()


@router.get('/health')
async def health() -> dict:
    return {'status': 'ok', 'timestamp': datetime.now(timezone.utc).isoformat()}
