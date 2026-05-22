import json
import logging
import os
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from app.models.event import ParsedEvent
from app.utils.retry import retry

logger = logging.getLogger(__name__)

TIMEZONE = 'America/Chicago'
_TZ = ZoneInfo(TIMEZONE)
SCOPES = ['https://www.googleapis.com/auth/calendar']
_CALENDAR_ID: str = ''
_service = None
_creds: Credentials | None = None
_last_token: str = ''


def _persist_token_if_refreshed() -> None:
    """If the credentials token has changed since last check, auto-update Railway."""
    global _last_token
    if _creds is None:
        return
    current_token = _creds.token or ''
    if current_token and current_token != _last_token:
        _last_token = current_token
        new_json = _creds.to_json()
        logger.warning(f'TOKEN_REFRESHED: {new_json}')
        from app.utils.railway import update_variable
        update_variable('GOOGLE_TOKEN_JSON', new_json)


def init_calendar_service() -> None:
    global _service, _creds, _CALENDAR_ID, _last_token

    _CALENDAR_ID = os.environ['GOOGLE_CALENDAR_ID']
    token_data = json.loads(os.environ['GOOGLE_TOKEN_JSON'])

    _creds = Credentials.from_authorized_user_info(token_data, SCOPES)

    if _creds.expired and _creds.refresh_token:
        _creds.refresh(Request())
        _last_token = _creds.token or ''
        new_json = _creds.to_json()
        logger.warning(f'TOKEN_REFRESHED: {new_json}')
        from app.utils.railway import update_variable
        update_variable('GOOGLE_TOKEN_JSON', new_json)
    else:
        _last_token = _creds.token or ''

    _service = build('calendar', 'v3', credentials=_creds)
    logger.info('Google Calendar service initialised')


def _svc():
    return _service


def _start_of_day(d: date) -> str:
    return datetime(d.year, d.month, d.day, 0, 0, 0, tzinfo=_TZ).isoformat()


def _end_of_day(d: date) -> str:
    return datetime(d.year, d.month, d.day, 23, 59, 59, tzinfo=_TZ).isoformat()


def _event_sort_key(event: dict) -> str:
    return event['start'].get('dateTime', event['start'].get('date', ''))


@retry(max_attempts=3, backoff_seconds=(5, 15, 45))
def create_event(event: ParsedEvent) -> str:
    date_parts = [int(x) for x in event.date.split('-')]
    time_parts = [int(x) for x in event.time.split(':')]
    start_dt = datetime(
        year=date_parts[0], month=date_parts[1], day=date_parts[2],
        hour=time_parts[0], minute=time_parts[1], tzinfo=_TZ,
    )
    end_dt = start_dt + timedelta(minutes=event.duration_minutes)

    body: dict = {
        'summary': event.title,
        'start': {'dateTime': start_dt.isoformat(), 'timeZone': TIMEZONE},
        'end':   {'dateTime': end_dt.isoformat(),   'timeZone': TIMEZONE},
    }
    if event.location:
        body['location'] = event.location

    result = _svc().events().insert(calendarId=_CALENDAR_ID, body=body).execute()
    _persist_token_if_refreshed()
    event_id = result.get('id', '')
    logger.info(f'phone=system event_title={event.title} event_date={event.date} calendar_event_id={event_id}')
    return event_id


@retry(max_attempts=3, backoff_seconds=(5, 15, 45))
def get_events_for_date(target_date: date) -> list:
    result = _svc().events().list(
        calendarId=_CALENDAR_ID,
        timeMin=_start_of_day(target_date),
        timeMax=_end_of_day(target_date),
        singleEvents=True,
        orderBy='startTime',
    ).execute()
    _persist_token_if_refreshed()
    return result.get('items', [])


@retry(max_attempts=3, backoff_seconds=(5, 15, 45))
def get_events_for_week(start: date) -> dict:
    end = start + timedelta(days=7)
    result = _svc().events().list(
        calendarId=_CALENDAR_ID,
        timeMin=_start_of_day(start),
        timeMax=_end_of_day(end),
        singleEvents=True,
        orderBy='startTime',
    ).execute()
    _persist_token_if_refreshed()
    items = result.get('items', [])

    week: dict = {}
    for i in range(7):
        week[start + timedelta(days=i)] = []

    for event in items:
        raw = event['start'].get('dateTime', event['start'].get('date', ''))
        try:
            dt = datetime.fromisoformat(raw)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=_TZ)
            event_date = dt.astimezone(_TZ).date()
            if event_date in week:
                week[event_date].append(event)
        except ValueError:
            pass

    return week


@retry(max_attempts=3, backoff_seconds=(5, 15, 45))
def search_events(keyword: str, days: int = 90) -> list:
    now = datetime.now(_TZ)
    end = now + timedelta(days=days)
    result = _svc().events().list(
        calendarId=_CALENDAR_ID,
        q=keyword,
        timeMin=now.isoformat(),
        timeMax=end.isoformat(),
        singleEvents=True,
        orderBy='startTime',
        maxResults=10,
    ).execute()
    _persist_token_if_refreshed()
    return result.get('items', [])


@retry(max_attempts=3, backoff_seconds=(5, 15, 45))
def get_event_detail(keyword: str) -> list:
    now = datetime.now(_TZ)
    end = now + timedelta(days=365)
    result = _svc().events().list(
        calendarId=_CALENDAR_ID,
        q=keyword,
        timeMin=now.isoformat(),
        timeMax=end.isoformat(),
        singleEvents=True,
        orderBy='startTime',
        maxResults=3,
    ).execute()
    _persist_token_if_refreshed()
    return result.get('items', [])
