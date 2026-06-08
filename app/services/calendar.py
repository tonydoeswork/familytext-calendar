import json
import logging
import os
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from google.oauth2 import service_account
from googleapiclient.discovery import build

from app.models.event import ParsedEvent
from app.utils.retry import retry

logger = logging.getLogger(__name__)

TIMEZONE = 'America/Chicago'
_TZ = ZoneInfo(TIMEZONE)
SCOPES = ['https://www.googleapis.com/auth/calendar']
_CALENDAR_ID: str = ''
_service = None


def init_calendar_service() -> None:
    global _service, _CALENDAR_ID

    try:
        _CALENDAR_ID = os.environ['GOOGLE_CALENDAR_ID']
        key_data = json.loads(os.environ['GOOGLE_SERVICE_ACCOUNT_JSON'])
        creds = service_account.Credentials.from_service_account_info(key_data, scopes=SCOPES)
        _service = build('calendar', 'v3', credentials=creds)
        logger.info('Google Calendar service initialised (service account)')

    except Exception as exc:
        logger.error(f'init_calendar_service failed: {exc}')
        from app.utils.alerts import alert_operator
        alert_operator(
            '[FamilyText] CRITICAL: Google Calendar auth failed at startup. '
            'App is dark. Check Railway logs & re-auth now.'
        )
        raise


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
    return result.get('items', [])
