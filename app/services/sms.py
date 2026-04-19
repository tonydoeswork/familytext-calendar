import logging
import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from twilio.rest import Client

from app.models.event import ParsedEvent

logger = logging.getLogger(__name__)

_client: Client | None = None
_TIMEZONE = ZoneInfo('America/Chicago')
_MAX_SMS_CHARS = 1600

HELP_TEXT = """FamilyText Calendar — Quick Guide

\u2795 Add: dentist Thursday 2pm
\U0001f4c5 Today: what's today
\U0001f4c6 Day: what's Friday / show me Apr 30
\U0001f5d3 Week: this week
\U0001f50d Search: do I have a dentist appt coming up
\u2139\ufe0f Details: details on dentist"""


def _get_client() -> Client:
    global _client
    if _client is None:
        _client = Client(os.environ['TWILIO_ACCOUNT_SID'], os.environ['TWILIO_AUTH_TOKEN'])
    return _client


def send_sms(to: str, body: str) -> None:
    if len(body) > _MAX_SMS_CHARS:
        body = body[:_MAX_SMS_CHARS]
    try:
        message = _get_client().messages.create(
            body=body,
            from_=os.environ['TWILIO_PHONE_NUMBER'],
            to=to,
        )
        logger.info(f"to={to} message_sid={message.sid} body_length={len(body)}")
    except Exception as exc:
        logger.error(f"Failed to send SMS to={to}: {exc}")


# ── display helpers ───────────────────────────────────────────────────────────

def _format_time_12h(dt: datetime) -> str:
    hour = dt.hour % 12 or 12
    minute = f'{dt.minute:02d}'
    ampm = 'AM' if dt.hour < 12 else 'PM'
    return f'{hour}:{minute} {ampm}'


def _format_date_short(dt: datetime) -> str:
    day_abbr = dt.strftime('%a')
    month_abbr = dt.strftime('%b')
    return f'{day_abbr} {month_abbr} {dt.day}'


def _parse_google_start(event: dict) -> datetime | None:
    # Only parse timed events; all-day events have start.date but no start.dateTime
    dt_str = event.get('start', {}).get('dateTime')
    if dt_str is None:
        return None
    try:
        dt = datetime.fromisoformat(dt_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=_TIMEZONE)
        return dt.astimezone(_TIMEZONE)
    except ValueError:
        return None


def _format_date_str(date_str: str) -> str:
    try:
        dt = datetime.strptime(date_str, '%Y-%m-%d')
        return f'{dt.strftime("%a")} {dt.strftime("%b")} {dt.day}'
    except ValueError:
        return date_str


def _format_time_str(time_str: str) -> str:
    try:
        h, m = (int(x) for x in time_str.split(':'))
        hour = h % 12 or 12
        ampm = 'AM' if h < 12 else 'PM'
        return f'{hour}:{m:02d} {ampm}'
    except (ValueError, AttributeError):
        return time_str


def _end_time_str(time_str: str, duration_minutes: int) -> str:
    try:
        h, m = (int(x) for x in time_str.split(':'))
        end = datetime(2000, 1, 1, h, m) + timedelta(minutes=duration_minutes)
        return _format_time_12h(end)
    except (ValueError, AttributeError):
        return ''


# ── formatters ────────────────────────────────────────────────────────────────

def format_event_list(events: list) -> str:
    lines = []
    for event in events:
        title = event.get('summary', 'Untitled')
        location = event.get('location', '')
        dt = _parse_google_start(event)

        if dt:
            time_part = _format_time_12h(dt)
        else:
            time_part = 'All day'

        line = f'{time_part} \u00b7 {title}'
        if location:
            line += f' ({location})'
        lines.append(line)
    return '\n'.join(lines)


def format_daily_summary(target_date: datetime, events: list) -> str:
    day_name = target_date.strftime('%A')
    month_name = target_date.strftime('%B')
    header = f'\u2600\ufe0f {day_name}, {month_name} {target_date.day}'
    if not events:
        return f'Good morning! Nothing on the calendar today.'
    return f'{header}\n\n{format_event_list(events)}'


def format_week_summary(week_dict: dict) -> str:
    parts = []
    for d in sorted(week_dict.keys()):
        events = week_dict[d]
        day_label = f'{d.strftime("%a")} {d.strftime("%b")} {d.day}'
        count = len(events)
        if count == 0:
            parts.append(f'{day_label}: none')
        elif count == 1:
            parts.append(f'{day_label}: 1 event')
        else:
            parts.append(f'{day_label}: {count} events')
    return ' \u00b7 '.join(parts) + '\nReply with a day for details.'


def format_confirmation_prompt(event: ParsedEvent) -> str:
    date_display = _format_date_str(event.date) if event.date else 'no date set'
    time_display = _format_time_str(event.time) if event.time else 'no time set'
    location_part = f' \u00b7 {event.location}' if event.location else ''
    return (
        f'I have: {event.title} \u00b7 {date_display} \u00b7 {time_display}{location_part}\n'
        f'Reply YES to confirm or NO to cancel.'
    )


def format_clarification_prompt(event: ParsedEvent, missing_field: str) -> str:
    date_display = _format_date_str(event.date) if event.date else 'no date set'
    time_display = _format_time_str(event.time) if event.time else 'no time set'
    title = event.title or 'event'

    if missing_field == 'time':
        return f'I have: {title} \u00b7 {date_display} \u00b7 no time set. What time?'
    if missing_field == 'date':
        return f'I have: {title} \u00b7 no date set \u00b7 {time_display}. What day?'
    if missing_field == 'title':
        return "What event should I add? (e.g., 'dentist Tuesday 2pm')"
    return f"What's the {missing_field}?"


def format_event_confirmation(event: ParsedEvent) -> str:
    date_display = _format_date_str(event.date)
    time_display = _format_time_str(event.time)
    end_display = _end_time_str(event.time, event.duration_minutes)
    msg = f'\u2705 Added: {event.title}\n\U0001f4c5 {date_display} \u00b7 {time_display}'
    if end_display:
        msg += f' \u2013 {end_display}'
    if event.location:
        msg += f'\n\U0001f4cd {event.location}'
    return msg


def format_event_detail(event: dict) -> str:
    title = event.get('summary', 'Untitled')
    dt = _parse_google_start(event)
    end_raw = event.get('end', {}).get('dateTime') or event.get('end', {}).get('date', '')
    location = event.get('location', '')
    description = event.get('description', '')
    created_raw = event.get('created', '')

    date_str = _format_date_short(dt) if dt else 'Unknown date'
    time_str = _format_time_12h(dt) if dt else 'All day'

    try:
        end_dt = datetime.fromisoformat(end_raw).astimezone(_TIMEZONE)
        end_str = _format_time_12h(end_dt)
    except (ValueError, AttributeError):
        end_str = ''

    lines = [f'{title}', f'\U0001f4c5 {date_str} \u00b7 {time_str}' + (f' \u2013 {end_str}' if end_str else '')]
    if location:
        lines.append(f'\U0001f4cd {location}')
    if description:
        lines.append(f'\U0001f4dd {description}')
    if created_raw:
        try:
            created_dt = datetime.fromisoformat(created_raw.replace('Z', '+00:00'))
            lines.append(f'Added: {created_dt.astimezone(_TIMEZONE).strftime("%b %d %Y")}')
        except ValueError:
            pass
    return '\n'.join(lines)
