"""Public, UNAUTHENTICATED catalog/pricing endpoint.

This is the single source of truth for accommodation units, prices, SPA services
and booking policies. The website (balandda.uz) and the CRM read from here instead
of keeping their own copies, so a price changed in the admin dashboard updates
everywhere at once.

Only safe, public data is exposed here (names, prices, capacities, policies).
Nothing requires auth; all write/admin operations stay in admin_catalog.py.
"""

from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import settings
from db.database import get_session
from db.enums import PROPERTY_TYPE_LABELS, PropertyType, ReservationStatus
from db.models import BusinessUnit, Property, Reservation, ServiceItem

router = APIRouter()

# Map each property type to the website page that represents it.
# NOTE: the site currently serves "Shale with/without sauna" from one page
# (cottage-shale.html), so both chalet types point at it and the page price is
# the lowest ("from") of the two. Split the page later to show them separately.
TYPE_TO_WEB_SLUG: dict[PropertyType, str] = {
    PropertyType.CHALET_WITH_SAUNA: "cottage-shale.html",
    PropertyType.CHALET_WITHOUT_SAUNA: "cottage-shale.html",
    PropertyType.WHITE_CHALET: "cottage-oq-shale.html",
    PropertyType.APARTMENT: "cottage-apartments.html",
    PropertyType.PENTHOUSE: "cottage-penthouse.html",
    PropertyType.VILLA: "cottage-villa.html",
    PropertyType.SPA_SUITE: "cottage-spa-suite.html",
}

# Booking policies. TODO: move these to an editable settings table so the owner
# can change them from the dashboard (Phase 1 follow-up).
POLICIES = {
    "check_in": "14:00",
    "check_out": "12:00",
    "prepayment_percent": 30,
    "cancellation": {
        "ru": "Бесплатная отмена за 7 дней до заезда. Позже — предоплата не возвращается.",
        "uz": "Kelishdan 7 kun oldin bepul bekor qilish. Keyin — oldindan to'lov qaytarilmaydi.",
    },
}


def _i(value) -> int:
    """Numeric/Decimal -> int UZS (sums have no fractional tiyin in practice)."""
    try:
        return int(round(float(value)))
    except (TypeError, ValueError):
        return 0


@router.get("/catalog")
async def public_catalog(
    response: Response,
    session: AsyncSession = Depends(get_session),
):
    """Single source of truth for accommodation + SPA pricing.

    Returns:
      - units:   every active bookable unit with its own weekday/weekend price
      - types:   units grouped by type, with the "from" price per type + web_slug
      - pages:   {website-filename: {weekday, weekend}} — drop-in for data/rates.json
      - spa:     active SPA/massage services with prices
      - policies: check-in/out, prepayment %, cancellation text
    """
    prop_rows = (
        await session.execute(
            select(Property)
            .where(Property.is_active.is_(True))
            .where(Property.business_unit == BusinessUnit.RESORT)
            .order_by(Property.sort_order)
        )
    ).scalars().all()

    units = []
    for p in prop_rows:
        units.append(
            {
                "code": p.code,
                "unit_number": p.unit_number,
                "type": p.property_type.value,
                "type_label": PROPERTY_TYPE_LABELS.get(p.property_type, p.property_type.value),
                "web_slug": TYPE_TO_WEB_SLUG.get(p.property_type),
                "name": {"ru": p.name_ru, "uz": p.name_uz},
                "capacity": p.capacity,
                "has_sauna": p.has_sauna,
                "emoji": p.emoji,
                "price": {"weekday": _i(p.price_weekday), "weekend": _i(p.price_weekend)},
            }
        )

    # Aggregate by type: "from" (minimum) price, capacity range, unit count.
    types: dict[str, dict] = {}
    for u in units:
        t = u["type"]
        agg = types.get(t)
        if agg is None:
            types[t] = {
                "type": t,
                "label": u["type_label"],
                "web_slug": u["web_slug"],
                "units": 1,
                "capacity_max": u["capacity"],
                "has_sauna": u["has_sauna"],
                "price_from": dict(u["price"]),
            }
        else:
            agg["units"] += 1
            agg["capacity_max"] = max(agg["capacity_max"], u["capacity"])
            agg["has_sauna"] = agg["has_sauna"] or u["has_sauna"]
            agg["price_from"]["weekday"] = min(agg["price_from"]["weekday"], u["price"]["weekday"])
            agg["price_from"]["weekend"] = min(agg["price_from"]["weekend"], u["price"]["weekend"])

    # Drop-in replacement for the website's data/rates.json (lowest price per page).
    pages: dict[str, dict] = {}
    for u in units:
        slug = u["web_slug"]
        if not slug:
            continue
        cur = pages.get(slug)
        if cur is None:
            pages[slug] = dict(u["price"])
        else:
            cur["weekday"] = min(cur["weekday"], u["price"]["weekday"])
            cur["weekend"] = min(cur["weekend"], u["price"]["weekend"])

    spa_rows = (
        await session.execute(
            select(ServiceItem).where(ServiceItem.is_active.is_(True)).order_by(ServiceItem.sort_order)
        )
    ).scalars().all()
    spa = [
        {
            "code": s.service_type.value,
            "name": {"ru": s.name_ru, "uz": s.name_uz},
            "duration_minutes": s.duration_minutes,
            "price": _i(s.price),
        }
        for s in spa_rows
    ]

    # Let clients (website/CRM) cache for a few minutes.
    response.headers["Cache-Control"] = "public, max-age=300"

    return {
        "currency": "UZS",
        "updated": datetime.now(timezone.utc).isoformat(),
        "units": units,
        "types": list(types.values()),
        "pages": pages,
        "spa": spa,
        "policies": POLICIES,
    }


def _stay_total(price_weekday, price_weekend, ci: date, co: date) -> int:
    """Sum nightly prices over the stay. Saturday = weekend rate; Sunday counts
    as a weekday (per Balandda pricing). Holidays are confirmed by the operator."""
    total = 0.0
    d = ci
    while d < co:
        total += float(price_weekend if d.weekday() == 5 else price_weekday)
        d += timedelta(days=1)
    return int(round(total))


@router.get("/availability")
async def public_availability(
    check_in: date,
    check_out: date,
    guests: int = 1,
    session: AsyncSession = Depends(get_session),
):
    """Units free for the whole [check_in, check_out) range, with the stay price.

    A unit is unavailable if any non-cancelled reservation overlaps the range.
    """
    if check_out <= check_in:
        return {"error": "check_out must be after check_in",
                "nights": 0, "available_units": [], "available_types": []}

    busy = (
        select(Reservation.property_id)
        .where(Reservation.check_in < check_out)
        .where(Reservation.check_out > check_in)
        .where(Reservation.status.notin_([ReservationStatus.CANCELLED, ReservationStatus.NO_SHOW]))
    )
    rows = (
        await session.execute(
            select(Property)
            .where(Property.is_active.is_(True))
            .where(Property.business_unit == BusinessUnit.RESORT)
            .where(Property.capacity >= guests)
            .where(Property.id.notin_(busy))
            .order_by(Property.sort_order)
        )
    ).scalars().all()

    nights = (check_out - check_in).days
    units = []
    for p in rows:
        total = _stay_total(p.price_weekday, p.price_weekend, check_in, check_out)
        units.append({
            "code": p.code,
            "type": p.property_type.value,
            "type_label": PROPERTY_TYPE_LABELS.get(p.property_type, p.property_type.value),
            "web_slug": TYPE_TO_WEB_SLUG.get(p.property_type),
            "name": {"ru": p.name_ru, "uz": p.name_uz},
            "capacity": p.capacity,
            "has_sauna": p.has_sauna,
            "price_total": total,
        })

    types: dict[str, dict] = {}
    for u in units:
        t = u["type"]
        agg = types.get(t)
        if agg is None:
            types[t] = {
                "type": t, "label": u["type_label"], "web_slug": u["web_slug"],
                "units_available": 1, "capacity_max": u["capacity"],
                "price_from_total": u["price_total"],
            }
        else:
            agg["units_available"] += 1
            agg["capacity_max"] = max(agg["capacity_max"], u["capacity"])
            agg["price_from_total"] = min(agg["price_from_total"], u["price_total"])

    return {
        "check_in": check_in.isoformat(),
        "check_out": check_out.isoformat(),
        "nights": nights,
        "guests": guests,
        "currency": "UZS",
        "available_units": units,
        "available_types": list(types.values()),
    }


@router.get("/login-config")
async def login_config(request: Request):
    """Which Telegram Login Widget bot the page should use, by domain.

    calendar.balandda.uz -> front-office bot; everything else -> main bot.
    """
    host = (request.headers.get("host") or "").split(":")[0].lower()
    if settings.front_bot_username and host.startswith("calendar."):
        return {"bot_login": settings.front_bot_username}
    return {"bot_login": settings.main_bot_username}
