"""Booking date rules — single source of truth for every channel.

Three rules, enforced here and pushed to OTAs by services/beds24.py:
  1. No past check-ins ("today" = Asia/Tashkent, not server UTC).
  2. Rolling sales window: bookings open only `booking_window_months` ahead
     (AppSetting, default 9 — editable in the dashboard).
  3. Admin-blocked periods (BlockedPeriod): resort-wide or per-unit.

The website's book.php and the calendar UIs use the same rules via
GET /api/v1/public/booking-rules; this module is the authoritative check
used by the bridge booking endpoints, so hand-crafted requests are
rejected even if a client UI misbehaves.
"""

from datetime import date, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import AppSetting, BlockedPeriod

TZ = ZoneInfo("Asia/Tashkent")
WINDOW_KEY = "booking_window_months"
DEFAULT_WINDOW_MONTHS = 9
MAX_NIGHTS = 30


def today_local() -> date:
    """Business 'today' in resort time (server runs UTC; Tashkent is UTC+5)."""
    from datetime import datetime

    return datetime.now(TZ).date()


def add_months(d: date, months: int) -> date:
    """Calendar-safe month addition (Jan 31 + 1m -> Feb 28/29)."""
    y = d.year + (d.month - 1 + months) // 12
    m = (d.month - 1 + months) % 12 + 1
    day = min(d.day, [31, 29 if y % 4 == 0 and (y % 100 != 0 or y % 400 == 0) else 28,
                      31, 30, 31, 30, 31, 31, 30, 31, 30, 31][m - 1])
    return date(y, m, day)


async def get_window_months(session: AsyncSession) -> int:
    row = await session.get(AppSetting, WINDOW_KEY)
    try:
        months = int(row.value) if row else DEFAULT_WINDOW_MONTHS
    except (TypeError, ValueError):
        months = DEFAULT_WINDOW_MONTHS
    return max(1, min(months, 24))


async def get_max_date(session: AsyncSession) -> date:
    """Last date open for sale (check-in must be <= this)."""
    return add_months(today_local(), await get_window_months(session))


async def get_blocked(session: AsyncSession, *, include_past: bool = False) -> list[BlockedPeriod]:
    q = select(BlockedPeriod).order_by(BlockedPeriod.date_from)
    if not include_past:
        q = q.where(BlockedPeriod.date_to >= today_local() - timedelta(days=1))
    return list((await session.execute(q)).scalars().all())


def block_hits_stay(b: BlockedPeriod, check_in: date, check_out: date, property_id: int | None) -> bool:
    """True when the block closes any NIGHT of the stay [check_in, check_out).

    Resort-wide blocks (property_id None) hit every unit; unit blocks hit
    only their unit. Checking out on the first day of a block is allowed
    (that night is not consumed).
    """
    if b.property_id is not None and b.property_id != property_id:
        return False
    return check_in <= b.date_to and check_out > b.date_from


async def validate_stay(
    session: AsyncSession,
    property_id: int | None,
    check_in: date,
    check_out: date,
) -> str | None:
    """Return an error code or None when the stay dates are bookable.

    Codes (shared with the website): dates_invalid | dates_past |
    dates_window | dates_blocked.
    """
    if check_out <= check_in or (check_out - check_in).days > MAX_NIGHTS:
        return "dates_invalid"
    if check_in < today_local():
        return "dates_past"
    if check_in > await get_max_date(session):
        return "dates_window"
    for b in await get_blocked(session):
        if block_hits_stay(b, check_in, check_out, property_id):
            return "dates_blocked"
    return None
