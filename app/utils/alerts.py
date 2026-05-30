import json
import logging
import os

logger = logging.getLogger(__name__)


def alert_operator(message: str) -> None:
    """Send an SMS alert directly to the operator (first entry in REGISTERED_USERS).

    Calls Twilio directly — intentionally does NOT go through send_sms() to
    avoid any recursion when send_sms() itself is the failure being reported.
    Wrapped in a bare try/except so a broken alert can never take down the caller.
    """
    try:
        raw = os.environ.get('REGISTERED_USERS', '[]')
        users = json.loads(raw)
        if not users:
            logger.error('alert_operator: REGISTERED_USERS is empty — cannot send alert')
            return
        operator_phone = users[0]['phone']

        from twilio.rest import Client
        client = Client(os.environ['TWILIO_ACCOUNT_SID'], os.environ['TWILIO_AUTH_TOKEN'])
        client.messages.create(
            body=message,
            from_=os.environ['TWILIO_PHONE_NUMBER'],
            to=operator_phone,
        )
        logger.info(f'alert_operator: alert sent to operator ({operator_phone[-4:]})')
    except Exception as exc:
        logger.error(f'alert_operator failed (cannot deliver alert): {exc}')
