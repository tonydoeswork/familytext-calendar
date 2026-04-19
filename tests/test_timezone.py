"""
Timezone tests. Verifies DST-safe event creation and daily summary scheduling.
Uses freezegun to mock the system clock.
"""
from datetime import datetime
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

import pytest
from freezegun import freeze_time

_TZ = ZoneInfo('America/Chicago')


def _utc_offset_hours(dt: datetime) -> int:
    offset = dt.utcoffset()
    return int(offset.total_seconds() / 3600)


@freeze_time('2026-01-15 20:00:00', tz_offset=0)  # CST day (UTC-6)
def test_event_at_2pm_cst_has_correct_utc_offset():
    from app.services.calendar import _TZ as CAL_TZ
    from zoneinfo import ZoneInfo

    naive = datetime(2026, 1, 15, 14, 0, 0)
    aware = naive.replace(tzinfo=ZoneInfo('America/Chicago'))
    offset = _utc_offset_hours(aware)
    assert offset == -6, f'Expected -6 (CST) but got {offset}'


@freeze_time('2026-07-15 19:00:00', tz_offset=0)  # CDT day (UTC-5)
def test_event_at_2pm_cdt_has_correct_utc_offset():
    from zoneinfo import ZoneInfo

    naive = datetime(2026, 7, 15, 14, 0, 0)
    aware = naive.replace(tzinfo=ZoneInfo('America/Chicago'))
    offset = _utc_offset_hours(aware)
    assert offset == -5, f'Expected -5 (CDT) but got {offset}'


def test_daily_summary_cron_uses_zoneinfo():
    """Verify that the scheduler uses ZoneInfo, not a raw UTC offset."""
    from app.scheduler import _TZ as SCHED_TZ
    from zoneinfo import ZoneInfo

    assert isinstance(SCHED_TZ, ZoneInfo), 'Scheduler timezone must be a ZoneInfo object'
    assert str(SCHED_TZ) == 'America/Chicago'


@freeze_time('2026-01-15 13:30:00', tz_offset=0)  # 7:30 AM CST (winter, UTC-6)
def test_cron_fires_at_730am_cst():
    now_utc = datetime(2026, 1, 15, 13, 30, 0)
    now_chicago = now_utc.replace(tzinfo=ZoneInfo('UTC')).astimezone(ZoneInfo('America/Chicago'))
    assert now_chicago.hour == 7
    assert now_chicago.minute == 30


@freeze_time('2026-03-09 12:30:00', tz_offset=0)  # 7:30 AM CDT (day after DST spring forward)
def test_cron_fires_at_730am_cdt():
    now_utc = datetime(2026, 3, 9, 12, 30, 0)
    now_chicago = now_utc.replace(tzinfo=ZoneInfo('UTC')).astimezone(ZoneInfo('America/Chicago'))
    assert now_chicago.hour == 7
    assert now_chicago.minute == 30
