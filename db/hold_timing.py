"""Working-hours math for unpaid-hold expiry.

An unpaid booking hold should warn after 30 min and expire after 60 min of
*working time* (09:00–21:00 Asia/Tashkent) — a hold created near closing carries
over to the next morning instead of expiring overnight. We compute the absolute
warn/expire timestamps once at creation (skipping non-working time), so the
scheduler only has to compare `now >= target`.
"""

from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from bot.config import settings

WORK_START_HOUR = 9    # 09:00
WORK_END_HOUR = 21     # 21:00
_TZ = ZoneInfo(settings.timezone)
_UTC = ZoneInfo("UTC")


def _to_next_open(dt: datetime) -> datetime:
    """Advance dt (local tz) to the next instant inside working hours."""
    if dt.hour >= WORK_END_HOUR:
        nxt = dt + timedelta(days=1)
        return nxt.replace(hour=WORK_START_HOUR, minute=0, second=0, microsecond=0)
    if dt.hour < WORK_START_HOUR:
        return dt.replace(hour=WORK_START_HOUR, minute=0, second=0, microsecond=0)
    return dt


def add_working_minutes(start: datetime, minutes: int) -> datetime:
    """Return the UTC timestamp reached after `minutes` of working time from `start`.

    `start` may be naive (assumed UTC) or tz-aware. Result is tz-aware UTC.
    """
    if start.tzinfo is None:
        start = start.replace(tzinfo=_UTC)
    cur = _to_next_open(start.astimezone(_TZ))
    remaining = timedelta(minutes=minutes)
    # Cap the loop; 60 working-minutes never spans more than a couple of days.
    for _ in range(400):
        if remaining <= timedelta(0):
            break
        close = cur.replace(hour=WORK_END_HOUR, minute=0, second=0, microsecond=0)
        avail = close - cur
        if remaining <= avail:
            cur = cur + remaining
            remaining = timedelta(0)
        else:
            remaining -= avail
            nxt = cur + timedelta(days=1)
            cur = nxt.replace(hour=WORK_START_HOUR, minute=0, second=0, microsecond=0)
    return cur.astimezone(_UTC)
