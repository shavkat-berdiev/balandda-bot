"""Nightly price resolution — the single source of truth for what a night costs.

Everything that shows or charges an accommodation price goes through here:
the public catalog + availability endpoints, the bridge booking endpoints, the
operator calendar API, and the Beds24 push that feeds Booking.com, Ostrovok,
Airbnb and Google Hotel Ads. Before this module the rule
``price_weekend if d.weekday() == 5 else price_weekday`` was copy-pasted in six
places; now it lives once, right here.

Resolution for (unit U, night D):

  1. Among ACTIVE seasons whose period covers D and that carry a price row for
     U, take the highest ``priority``; ties break on the shorter period, then
     the lower season id. New Year is just a season with priority 100.
  2. No season → the base rate on ``properties`` (the high-season rate).
  3. Band inside the chosen row: the WEEKEND price when D is a Saturday **or**
     an active holiday; otherwise the WEEKDAY price. Sunday is a weekday, which
     is what the price tables have always promised guests.

Usage — load the index once per request, then look up for free::

    idx = await load_rate_index(session, check_in, check_out)
    total = stay_total(idx, prop.id, check_in, check_out)
"""

from dataclasses import dataclass, field
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import Holiday, Property, RateSeason, RateSeasonPeriod, RateSeasonPrice

SATURDAY = 5  # date.weekday(): Mon=0 … Sat=5, Sun=6


@dataclass
class SeasonWindow:
    """One resolved date range of a season, with its per-unit prices."""

    season_id: int
    name: str
    priority: int
    date_from: date
    date_to: date  # inclusive
    prices: dict[int, tuple[float, float]] = field(default_factory=dict)  # property_id -> (wd, we)

    @property
    def span(self) -> int:
        return (self.date_to - self.date_from).days

    def covers(self, d: date) -> bool:
        return self.date_from <= d <= self.date_to


@dataclass
class RateIndex:
    """Everything needed to price any night in the loaded window."""

    base: dict[int, tuple[float, float]] = field(default_factory=dict)  # property_id -> (wd, we)
    windows: list[SeasonWindow] = field(default_factory=list)
    holidays: dict[date, str] = field(default_factory=dict)

    def is_weekend_band(self, d: date) -> bool:
        """Saturday or an active holiday → the weekend (higher) rate."""
        return d.weekday() == SATURDAY or d in self.holidays

    def window_for(self, property_id: int, d: date) -> SeasonWindow | None:
        """The winning season window for this unit/night, or None for base rate."""
        best: SeasonWindow | None = None
        for w in self.windows:
            if not w.covers(d) or property_id not in w.prices:
                continue
            if best is None or (
                (w.priority, -w.span, -w.season_id)
                > (best.priority, -best.span, -best.season_id)
            ):
                best = w
        return best


async def load_rate_index(
    session: AsyncSession,
    start: date,
    end: date,
    *,
    property_ids: list[int] | None = None,
) -> RateIndex:
    """Load base rates, overlapping seasons and holidays for [start, end).

    `end` is exclusive (it is a check-out date), so the last priced night is
    end - 1 day. One query set regardless of how many nights are involved.
    """
    last_night = end - timedelta(days=1) if end > start else start

    q = select(Property.id, Property.price_weekday, Property.price_weekend)
    if property_ids is not None:
        q = q.where(Property.id.in_(property_ids))
    base = {
        pid: (float(wd or 0), float(we or 0))
        for pid, wd, we in (await session.execute(q)).all()
    }

    # Column-only selects on purpose: RateSeason.periods/.prices are
    # lazy="selectin", so loading the ORM entity here would fire extra queries
    # on every catalog hit, every booking write and every OTA push.
    period_rows = (
        await session.execute(
            select(
                RateSeason.id,
                RateSeason.name,
                RateSeason.priority,
                RateSeasonPeriod.date_from,
                RateSeasonPeriod.date_to,
            )
            .join(RateSeason, RateSeason.id == RateSeasonPeriod.season_id)
            .where(RateSeason.is_active.is_(True))
            .where(RateSeasonPeriod.date_from <= last_night)
            .where(RateSeasonPeriod.date_to >= start)
        )
    ).all()

    season_ids = {r[0] for r in period_rows}
    prices: dict[int, dict[int, tuple[float, float]]] = {}
    if season_ids:
        for sid, pid, wd, we in (
            await session.execute(
                select(
                    RateSeasonPrice.season_id,
                    RateSeasonPrice.property_id,
                    RateSeasonPrice.price_weekday,
                    RateSeasonPrice.price_weekend,
                ).where(RateSeasonPrice.season_id.in_(season_ids))
            )
        ).all():
            prices.setdefault(sid, {})[pid] = (float(wd or 0), float(we or 0))

    windows = [
        SeasonWindow(
            season_id=sid,
            name=name,
            priority=priority or 0,
            date_from=date_from,
            date_to=date_to,
            prices=prices.get(sid, {}),
        )
        for sid, name, priority, date_from, date_to in period_rows
    ]

    holidays = {
        d: (n or "")
        for d, n in (
            await session.execute(
                select(Holiday.date, Holiday.name)
                .where(Holiday.is_active.is_(True))
                .where(Holiday.date >= start)
                .where(Holiday.date <= last_night)
            )
        ).all()
    }

    return RateIndex(base=base, windows=windows, holidays=holidays)


def nightly_price(idx: RateIndex, property_id: int, d: date) -> int:
    """What this unit costs for the night of `d`, in UZS."""
    w = idx.window_for(property_id, d)
    pair = w.prices[property_id] if w else idx.base.get(property_id, (0.0, 0.0))
    return int(round(pair[1] if idx.is_weekend_band(d) else pair[0]))


def stay_total(idx: RateIndex, property_id: int, ci: date, co: date) -> int:
    """Sum of nightly prices over [ci, co). Zero for an empty or invalid range."""
    if co <= ci:
        return 0
    total = 0
    d = ci
    while d < co:
        total += nightly_price(idx, property_id, d)
        d += timedelta(days=1)
    return total


def season_label(idx: RateIndex, property_id: int, d: date) -> str | None:
    """Name of the season pricing this night, or None when it is the base rate."""
    w = idx.window_for(property_id, d)
    return w.name if w else None


def price_periods(idx: RateIndex, property_ids: list[int]) -> list[dict]:
    """Season windows as flat dicts for the public API, using the cheapest
    ("from") price across the given units — mirrors how `types`/`pages` are
    aggregated in the public catalog."""
    out = []
    for w in sorted(idx.windows, key=lambda x: (x.date_from, -x.priority)):
        pairs = [w.prices[pid] for pid in property_ids if pid in w.prices]
        if not pairs:
            continue
        out.append(
            {
                "from": w.date_from.isoformat(),
                "to": w.date_to.isoformat(),
                "weekday": int(round(min(p[0] for p in pairs))),
                "weekend": int(round(min(p[1] for p in pairs))),
                "season": w.name,
                "priority": w.priority,
            }
        )
    return out


async def freeze_open_totals(session: AsyncSession) -> int:
    """Write today's computed total onto every future reservation that has none.

    `total_amount` is a snapshot taken at booking time, but three read paths in
    reservations.py fall back to a LIVE recompute when it is NULL — so bookings
    created by reservation_sync.py would silently re-price the moment a season
    goes live. Run this once before activating a season. Returns rows updated.
    """
    from db.booking_rules import today_local
    from db.enums import ReservationStatus
    from db.models import Reservation

    today = today_local()
    rows = (
        await session.execute(
            select(Reservation)
            .where(Reservation.check_out >= today)
            .where(Reservation.total_amount.is_(None))
            # BLOCKED (maintenance/owner holds) and EXPIRED carry no money and
            # must stay NULL — the calendar colours a block by its paid ratio,
            # so stamping a total on one would paint it as an unpaid booking.
            .where(
                Reservation.status.notin_(
                    [
                        ReservationStatus.CANCELLED,
                        ReservationStatus.NO_SHOW,
                        ReservationStatus.BLOCKED,
                        ReservationStatus.EXPIRED,
                    ]
                )
            )
        )
    ).scalars().all()
    if not rows:
        return 0

    lo = min(r.check_in for r in rows)
    hi = max(r.check_out for r in rows)
    idx = await load_rate_index(session, lo, hi)

    n = 0
    for r in rows:
        if not r.property_id or not r.check_in or not r.check_out:
            continue
        total = stay_total(idx, r.property_id, r.check_in, r.check_out)
        if total > 0:
            pct = float(r.discount_percent or 0)
            r.total_amount = round(total * (1 - pct / 100))
            n += 1
    await session.commit()
    return n
