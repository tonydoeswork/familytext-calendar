import logging
import os
from datetime import datetime
from zoneinfo import ZoneInfo

import anthropic

from app.models.event import ParsedEvent
from app.models.intent import Intent

logger = logging.getLogger(__name__)

MODEL = 'claude-haiku-4-5-20251001'
_client: anthropic.Anthropic | None = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=os.environ['ANTHROPIC_API_KEY'])
    return _client


# ── classify_intent ───────────────────────────────────────────────────────────

_CLASSIFY_SYSTEM = """\
You are an SMS intent classifier for a family calendar system.

Valid intents and examples:
- add: create a new calendar event ("dentist Thursday 2pm", "dinner Saturday 6pm", "pediatrician tuesday")
- query_today: ask for today's events ("what's today", "today's schedule", "what do I have today")
- query_date: ask for events on a specific date ("what's on Friday", "show me April 30", "what's tomorrow")
- query_week: ask for a week overview ("this week", "week view", "what's this week")
- query_detail: ask for details on a named event ("details on dentist", "tell me about pediatrician appt")
- query_search: search for events by keyword ("do I have a dentist appt coming up", "when is Rowan's next doctor appointment", "any gym sessions next month")
- confirm_yes: affirm a pending action (yes, yeah, yep, sure, ok, correct, right, yup)
- confirm_no: cancel a pending action (no, nope, cancel, nevermind, stop, nah)
- help: request usage guide (HELP, ?, how do I use this)
- recurring: request to add a repeating event ("soccer every Saturday", "weekly team lunch", "dentist every 6 months", "every other Tuesday at 3pm")
- unknown: cannot determine intent

Return exactly one intent value.\
"""


def classify_intent(message: str, has_pending_session: bool) -> Intent:
    pending_note = (
        '\n\nACTIVE SESSION: A confirmation or clarification is pending. '
        "Messages like 'yes', 'yeah', 'yep', 'sure', 'ok' → confirm_yes. "
        "Messages like 'no', 'nope', 'cancel', 'nevermind' → confirm_no."
        if has_pending_session else ''
    )

    try:
        resp = _get_client().messages.create(
            model=MODEL,
            max_tokens=64,
            system=[{
                'type': 'text',
                'text': _CLASSIFY_SYSTEM,
                'cache_control': {'type': 'ephemeral'},
            }],
            tools=[{
                'name': 'classify_intent',
                'description': 'Classify the intent of an SMS message',
                'input_schema': {
                    'type': 'object',
                    'properties': {
                        'intent': {
                            'type': 'string',
                            'enum': [i.value for i in Intent],
                        }
                    },
                    'required': ['intent'],
                },
            }],
            tool_choice={'type': 'tool', 'name': 'classify_intent'},
            messages=[{'role': 'user', 'content': message + pending_note}],
        )
        for block in resp.content:
            if block.type == 'tool_use':
                return Intent(block.input.get('intent', 'unknown'))
    except Exception as exc:
        logger.error(f'classify_intent failed: {exc}')
    return Intent.UNKNOWN


# ── parse_event ───────────────────────────────────────────────────────────────

_PARSE_SYSTEM = """\
You are an event parser for a family SMS calendar. Extract calendar event details from natural language.

Rules:
- Infer the event title from context if not explicit
- Resolve relative dates ("tomorrow", "next Tuesday", "this weekend") using today's date provided by the user
- Default duration: 60 minutes unless specified
- Time defaults: "morning" = 09:00, "this morning" = 09:00, "afternoon" = 14:00,
  "this afternoon" = 14:00, "evening" = 18:00, "tonight" = 19:00
- If a required field (title, date, time) is missing or truly unresolvable, add it to missing_fields
- If a field was parsed but with uncertainty (e.g. "Tuesday" when multiple upcoming Tuesdays exist),
  add it to ambiguous_fields
- Set confidence: high (all required fields clear), medium (ambiguous fields), low (missing fields)
- Set location to null if not mentioned — never omit it\
"""


def parse_event(message: str, timezone: str) -> ParsedEvent:
    tz = ZoneInfo(timezone)
    now = datetime.now(tz)
    today_context = (
        f'Today is {now.strftime("%A")}, {now.strftime("%B")} {now.day}, {now.year}. '
        f'Current time: {now.strftime("%H:%M")} {timezone}.\n\n'
        f'Parse this message: {message}'
    )

    try:
        resp = _get_client().messages.create(
            model=MODEL,
            max_tokens=512,
            system=[{
                'type': 'text',
                'text': _PARSE_SYSTEM,
                'cache_control': {'type': 'ephemeral'},
            }],
            tools=[{
                'name': 'parse_event',
                'description': 'Parse a natural language SMS into structured calendar event data',
                'input_schema': {
                    'type': 'object',
                    'properties': {
                        'title': {'type': 'string'},
                        'date': {'type': ['string', 'null'], 'description': 'ISO 8601 YYYY-MM-DD or null'},
                        'time': {'type': ['string', 'null'], 'description': '24-hour HH:MM or null'},
                        'duration_minutes': {'type': 'integer', 'description': 'Default 60'},
                        'location': {'type': ['string', 'null']},
                        'confidence': {'type': 'string', 'enum': ['high', 'medium', 'low']},
                        'missing_fields': {'type': 'array', 'items': {'type': 'string'}},
                        'ambiguous_fields': {'type': 'array', 'items': {'type': 'string'}},
                    },
                    'required': ['title', 'date', 'time', 'duration_minutes', 'location',
                                 'confidence', 'missing_fields', 'ambiguous_fields'],
                },
            }],
            tool_choice={'type': 'tool', 'name': 'parse_event'},
            messages=[{'role': 'user', 'content': today_context}],
        )
        for block in resp.content:
            if block.type == 'tool_use':
                d = block.input
                return ParsedEvent(
                    title=d.get('title') or 'Event',
                    date=d.get('date') or '',
                    time=d.get('time') or '',
                    duration_minutes=d.get('duration_minutes') or 60,
                    location=d.get('location'),
                    confidence=d.get('confidence', 'low'),
                    missing_fields=d.get('missing_fields', []),
                    ambiguous_fields=d.get('ambiguous_fields', []),
                    raw_message=message,
                )
    except Exception as exc:
        logger.error(f'parse_event failed: {exc}')

    return ParsedEvent(
        title='Event', date='', time='', raw_message=message,
        confidence='low', missing_fields=['title', 'date', 'time'],
    )


# ── query parameter extraction ────────────────────────────────────────────────

def extract_date_param(message: str) -> str | None:
    tz = ZoneInfo('America/Chicago')
    now = datetime.now(tz)
    context = (
        f'Today is {now.strftime("%A")}, {now.strftime("%B")} {now.day}, {now.year}.\n'
        f'Extract the target date from: {message}'
    )
    try:
        resp = _get_client().messages.create(
            model=MODEL,
            max_tokens=64,
            system=[{
                'type': 'text',
                'text': 'Extract the target calendar date from a query. Return ISO 8601 YYYY-MM-DD.',
                'cache_control': {'type': 'ephemeral'},
            }],
            tools=[{
                'name': 'extract_date',
                'description': 'Extract the queried date',
                'input_schema': {
                    'type': 'object',
                    'properties': {'date': {'type': 'string', 'description': 'YYYY-MM-DD'}},
                    'required': ['date'],
                },
            }],
            tool_choice={'type': 'tool', 'name': 'extract_date'},
            messages=[{'role': 'user', 'content': context}],
        )
        for block in resp.content:
            if block.type == 'tool_use':
                return block.input.get('date')
    except Exception as exc:
        logger.error(f'extract_date_param failed: {exc}')
    return None


def extract_search_params(message: str) -> dict:
    try:
        resp = _get_client().messages.create(
            model=MODEL,
            max_tokens=64,
            system=[{
                'type': 'text',
                'text': 'Extract a search keyword and optional day range from a calendar search query. Default days=90.',
                'cache_control': {'type': 'ephemeral'},
            }],
            tools=[{
                'name': 'extract_search',
                'description': 'Extract search parameters',
                'input_schema': {
                    'type': 'object',
                    'properties': {
                        'keyword': {'type': 'string'},
                        'days': {'type': 'integer', 'description': 'Search window in days, default 90'},
                    },
                    'required': ['keyword', 'days'],
                },
            }],
            tool_choice={'type': 'tool', 'name': 'extract_search'},
            messages=[{'role': 'user', 'content': message}],
        )
        for block in resp.content:
            if block.type == 'tool_use':
                return {'keyword': block.input.get('keyword', ''), 'days': block.input.get('days', 90)}
    except Exception as exc:
        logger.error(f'extract_search_params failed: {exc}')
    return {'keyword': message, 'days': 90}


def extract_detail_keyword(message: str) -> str:
    try:
        resp = _get_client().messages.create(
            model=MODEL,
            max_tokens=64,
            system=[{
                'type': 'text',
                'text': "Extract the event name or keyword from a detail query like 'details on dentist'.",
                'cache_control': {'type': 'ephemeral'},
            }],
            tools=[{
                'name': 'extract_keyword',
                'description': 'Extract the event keyword',
                'input_schema': {
                    'type': 'object',
                    'properties': {'keyword': {'type': 'string'}},
                    'required': ['keyword'],
                },
            }],
            tool_choice={'type': 'tool', 'name': 'extract_keyword'},
            messages=[{'role': 'user', 'content': message}],
        )
        for block in resp.content:
            if block.type == 'tool_use':
                return block.input.get('keyword', '')
    except Exception as exc:
        logger.error(f'extract_detail_keyword failed: {exc}')
    return message
