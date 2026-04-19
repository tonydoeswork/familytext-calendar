import logging
from datetime import date
from zoneinfo import ZoneInfo

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from app import config

logger = logging.getLogger(__name__)

_scheduler = BackgroundScheduler()
_TZ = ZoneInfo('America/Chicago')


def daily_summary_job() -> None:
    from app.services.calendar import get_events_for_date
    from app.services.sms import format_daily_summary, send_sms
    from datetime import datetime

    today = date.today()
    logger.info(f'Running daily summary for {today}')
    try:
        events = get_events_for_date(today)
        summary = format_daily_summary(datetime.now(_TZ), events)
        for phone in config.get_summary_recipients():
            send_sms(phone, summary)
    except Exception as exc:
        logger.error(f'daily_summary_job failed: {exc}')


def session_expiry_job() -> None:
    from app.services.session import check_expired_sessions
    try:
        check_expired_sessions()
    except Exception as exc:
        logger.error(f'session_expiry_job failed: {exc}')


def start_scheduler() -> None:
    hour, minute = config.get_summary_time()
    _scheduler.add_job(
        daily_summary_job,
        CronTrigger(hour=hour, minute=minute, timezone=_TZ),
        id='daily_summary',
        replace_existing=True,
    )
    _scheduler.add_job(
        session_expiry_job,
        IntervalTrigger(minutes=5),
        id='session_expiry',
        replace_existing=True,
    )
    _scheduler.start()
    logger.info('Scheduler started')


def stop_scheduler() -> None:
    _scheduler.shutdown(wait=False)
    logger.info('Scheduler stopped')
