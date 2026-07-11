"""Beds24 channel-manager sync (OTA bridge: Booking.com / Airbnb / Trip.com).

calendar.balandda.uz stays the single source of truth:
  • OUT: availability (numAvail) + daily USD prices for every room type are pushed
    to Beds24, which relays them to the connected OTAs. Prices = UZS nightly rate
    × (1 + markup%) ÷ UZS/USD rate (CBU auto or manual override), rounded up.
  • IN:  bookings made on OTAs land in Beds24; we poll them and create local
    reservations (source BOOKING_COM / AIRBNB / TRIP_COM), then push availability
    back so all other channels close the dates.

Everything is best-effort and gated by settings.beds24_enabled — a Beds24 outage
must never break the booking flow. Call kick() after any reservation write; it
coalesces bursts and runs one full push in the background.
"""

import asyncio
import logging
import math
import time
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

import aiohttp
from sqlalchemy import select

from bot.config import settings
from db.database import async_session
from db.enums import PropertyType, ReservationSource, ReservationStatus
from db.models import Property, Reservation, ReservationEvent

logger = logging.getLogger(__name__)

API = "https://api.beds24.com/v2"
CBU_URL = "https://cbu.uz/ru/arkhiv-kursov-valyut/json/USD/"
CBU_FALLBACK_RATE = 12000.0

# PropertyType.value → Beds24 roomId (property "Balandda Chimgan" id 340623)
ROOM_MAP: dict[str, int] = {
    PropertyType.CHALET_WITH_SAUNA.value: 704008,
    PropertyType.CHALET_WITHOUT_SAUNA.value: 704009,
    PropertyType.WHITE_CHALET.value: 704010,
    PropertyType.APARTMENT.value: 704011,
    PropertyType.SPA_SUITE.value: 704012,
    PropertyType.PENTHOUSE.value: 704013,
    PropertyType.VILLA.value: 704014,
}
ROOM_MAP_REV = {v: k for k, v in ROOM_MAP.items()}

# Statuses that occupy a unit (mirror of the reservations_no_overlap constraint)
OCCUPYING = [s for s in ReservationStatus
             if s not in (ReservationStatus.CANCELLED, ReservationStatus.NO_SHOW,
                          ReservationStatus.EXPIRED)]


def _enabled() -> bool:
    return bool(getattr(settings, "beds24_enabled", False)
                and getattr(settings, "beds24_refresh_token", ""))


# ── auth ────────────────────────────────────────────────────────────────────
_token_cache: dict = {"token": None, "exp": 0.0}


async def _get_token(s: aiohttp.ClientSession) -> str | None:
    if _token_cache["token"] and time.time() < _token_cache["exp"] - 300:
        return _token_cache["token"]
    try:
        async with s.get(f"{API}/authentication/token",
                         headers={"refreshToken": settings.beds24_refresh_token},
                         timeout=aiohttp.ClientTimeout(total=15)) as r:
            j = await r.json()
        if r.status < 400 and j.get("token"):
            _token_cache["token"] = j["token"]
            _token_cache["exp"] = time.time() + int(j.get("expiresIn") or 86400)
            return j["token"]
        logger.error("beds24 token refresh failed %s: %s", r.status, j)
    except Exception as e:  # noqa: BLE001
        logger.warning("beds24 token error: %s", e)
    return None


# ── USD rate ────────────────────────────────────────────────────────────────
_rate_cache: dict = {"rate": None, "ts": 0.0}


async def get_usd_rate(s: aiohttp.ClientSession) -> float:
    """UZS per USD: manual override from settings, else CBU official (cached 6h)."""
    manual = float(getattr(settings, "beds24_usd_rate", 0) or 0)
    if manual > 0:
        return manual
    if _rate_cache["rate"] and time.time() - _rate_cache["ts"] < 6 * 3600:
        return _rate_cache["rate"]
    try:
        async with s.get(CBU_URL, timeout=aiohttp.ClientTimeout(total=10)) as r:
            j = await r.json(content_type=None)
        rate = float(j[0]["Rate"])
        _rate_cache.update(rate=rate, ts=time.time())
        return rate
    except Exception as e:  # noqa: BLE001
        logger.warning("CBU rate fetch failed: %s", e)
        return _rate_cache["rate"] or CBU_FALLBACK_RATE


def _usd(uzs: float, rate: float) -> int:
    markup = float(getattr(settings, "beds24_markup_percent", 20) or 0)
    return max(1, math.ceil(float(uzs) * (1 + markup / 100.0) / rate))


# ── availability + price computation (single source: our DB) ───────────────
async def _compute_calendar(days: int) -> list[dict]:
    """Per Beds24 room: compressed [{from,to,numAvail,price1}] for the next `days`."""
    start = date.today()
    end = start + timedelta(days=days)

    async with async_session() as session:
        props = (await session.execute(
            select(Property).where(Property.is_active.is_(True))
        )).scalars().all()
        props = [p for p in props if p.property_type.value in ROOM_MAP]
        prop_type = {p.id: p.property_type.value for p in props}

        busy = (await session.execute(
            select(Reservation.property_id, Reservation.check_in, Reservation.check_out)
            .where(Reservation.check_out > start)
            .where(Reservation.check_in < end)
            .where(Reservation.status.in_(OCCUPYING))
            .where(Reservation.property_id.in_(list(prop_type.keys())))
        )).all()

    async with aiohttp.ClientSession() as s:
        rate = await get_usd_rate(s)

    # busy count per (type, date)
    busy_count: dict[tuple[str, date], int] = {}
    for pid, ci, co in busy:
        t = prop_type[pid]
        d = max(ci, start)
        stop = min(co, end)
        while d < stop:
            busy_count[(t, d)] = busy_count.get((t, d), 0) + 1
            d += timedelta(days=1)

    payload = []
    for tval, room_id in ROOM_MAP.items():
        units = [p for p in props if p.property_type.value == tval]
        if not units:
            continue
        total = len(units)
        price_wd = _usd(min(float(p.price_weekday or 0) for p in units) or 0, rate)
        price_we = _usd(min(float(p.price_weekend or 0) for p in units) or 0, rate)
        days_list = []
        d = start
        while d < end:
            n = max(0, total - busy_count.get((tval, d), 0))
            p1 = price_we if d.weekday() == 5 else price_wd  # Saturday = weekend rate
            days_list.append((d, n, p1))
            d += timedelta(days=1)
        # compress consecutive identical (numAvail, price) into ranges
        cal = []
        s0 = prev = days_list[0]
        for cur in days_list[1:]:
            if cur[1] == prev[1] and cur[2] == prev[2]:
                prev = cur
                continue
            cal.append({"from": s0[0].isoformat(), "to": prev[0].isoformat(),
                        "numAvail": s0[1], "price1": s0[2]})
            s0 = prev = cur
        cal.append({"from": s0[0].isoformat(), "to": prev[0].isoformat(),
                    "numAvail": s0[1], "price1": s0[2]})
        payload.append({"roomId": room_id, "calendar": cal})
    return payload


async def push_full() -> bool:
    """Push availability + prices for the whole sync window to Beds24."""
    if not _enabled():
        return False
    days = int(getattr(settings, "beds24_sync_days", 365) or 365)
    try:
        payload = await _compute_calendar(days)
        async with aiohttp.ClientSession() as s:
            token = await _get_token(s)
            if not token:
                return False
            async with s.post(f"{API}/inventory/rooms/calendar", json=payload,
                              headers={"token": token},
                              timeout=aiohttp.ClientTimeout(total=60)) as r:
                body = await r.json(content_type=None)
        ok = r.status < 400 and all(x.get("success") for x in body)
        if ok:
            logger.info("beds24 push_full ok (%d rooms, %d days)", len(payload), days)
        else:
            logger.error("beds24 push_full failed %s: %.500s", r.status, body)
        return ok
    except Exception as e:  # noqa: BLE001
        logger.warning("beds24 push_full error: %s", e)
        return False


# ── kick: coalesced fire-and-forget push after reservation writes ───────────
_kick_state = {"dirty": False, "task": None}


def kick() -> None:
    """Call after any reservation change. Never raises; no-op when disabled."""
    if not _enabled():
        return
    _kick_state["dirty"] = True
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    t = _kick_state["task"]
    if t is None or t.done():
        _kick_state["task"] = loop.create_task(_kick_worker())


async def _kick_worker():
    while _kick_state["dirty"]:
        _kick_state["dirty"] = False
        await asyncio.sleep(2)  # coalesce bursts
        await push_full()


# ── inbound: import OTA bookings from Beds24 ────────────────────────────────
def _map_source(b: dict) -> ReservationSource:
    hay = " ".join(str(b.get(k) or "") for k in ("referer", "apiSource", "channel", "origin")).lower()
    if "booking" in hay:
        return ReservationSource.BOOKING_COM
    if "airbnb" in hay:
        return ReservationSource.AIRBNB
    if "trip" in hay or "ctrip" in hay:
        return getattr(ReservationSource, "TRIP_COM", ReservationSource.MANUAL)
    return ReservationSource.MANUAL


async def pull_bookings() -> int:
    """Import new/changed OTA bookings from Beds24. Returns number of changes."""
    if not _enabled():
        return 0
    changed = 0
    since = (datetime.now(timezone.utc) - timedelta(days=3)).strftime("%Y-%m-%d %H:%M:%S")
    try:
        async with aiohttp.ClientSession() as s:
            token = await _get_token(s)
            if not token:
                return 0
            async with s.get(f"{API}/bookings",
                             params={"propertyId": str(getattr(settings, "beds24_property_id", 340623)),
                                     "modifiedFrom": since},
                             headers={"token": token},
                             timeout=aiohttp.ClientTimeout(total=30)) as r:
                j = await r.json(content_type=None)
        if r.status >= 400 or not j.get("success", True):
            logger.error("beds24 pull failed %s: %.300s", r.status, j)
            return 0
        bookings = j.get("data") or []
    except Exception as e:  # noqa: BLE001
        logger.warning("beds24 pull error: %s", e)
        return 0

    for b in bookings:
        try:
            changed += await _import_booking(b)
        except Exception as e:  # noqa: BLE001
            logger.error("beds24 import #%s failed: %s", b.get("id"), e, exc_info=True)
    if changed:
        kick()  # push updated availability back to all channels
    return changed


async def _import_booking(b: dict) -> int:
    bid = str(b.get("id") or "")
    room_id = b.get("roomId")
    status = str(b.get("status") or "").lower()
    if not bid or room_id not in ROOM_MAP_REV:
        return 0
    arrival = date.fromisoformat(b["arrival"])
    departure = date.fromisoformat(b["departure"])
    tval = ROOM_MAP_REV[room_id]
    src = _map_source(b)
    guest = " ".join(x for x in (b.get("firstName"), b.get("lastName")) if x).strip() or None
    phone = b.get("phone") or b.get("mobile") or None

    async with async_session() as session:
        existing = (await session.execute(
            select(Reservation).where(Reservation.channel_booking_id == bid)
        )).scalar_one_or_none()

        if status in ("cancelled", "black"):
            if existing and existing.status not in (ReservationStatus.CANCELLED,):
                existing.status = ReservationStatus.CANCELLED
                session.add(ReservationEvent(
                    reservation_id=existing.id, actor_name="Beds24", action="cancelled",
                    detail=f"Отменено на канале ({src.value}) · Beds24 #{bid}",
                ))
                await session.commit()
                return 1
            return 0

        if status not in ("new", "confirmed", "request"):
            return 0

        if existing:
            if (existing.check_in, existing.check_out) != (arrival, departure):
                existing.check_in, existing.check_out = arrival, departure
                session.add(ReservationEvent(
                    reservation_id=existing.id, actor_name="Beds24", action="updated",
                    detail=f"Даты изменены на канале · Beds24 #{bid}",
                ))
                await session.commit()
                return 1
            return 0

        # choose a free unit of this type for the dates
        busy = (
            select(Reservation.property_id)
            .where(Reservation.check_in < departure)
            .where(Reservation.check_out > arrival)
            .where(Reservation.status.in_(OCCUPYING))
        )
        unit = (await session.execute(
            select(Property)
            .where(Property.is_active.is_(True))
            .where(Property.property_type == PropertyType(tval))
            .where(Property.id.notin_(busy))
            .order_by(Property.sort_order)
        )).scalars().first()

        rate = _rate_cache["rate"] or CBU_FALLBACK_RATE
        price_usd = float(b.get("price") or 0)
        total_uzs = round(price_usd * rate) if price_usd else None
        note = f"Beds24 #{bid} · {src.value} · {price_usd:.0f} USD" if price_usd else f"Beds24 #{bid} · {src.value}"

        if unit is None:
            logger.error("beds24 OVERBOOK: no free %s for %s→%s (booking #%s)",
                         tval, arrival, departure, bid)
            session.add(ReservationEvent(
                reservation_id=None, actor_name="Beds24", action="ota_overbook",
                detail=f"⚠️ Нет свободного юнита {tval} на {arrival}—{departure} (Beds24 #{bid}, {src.value})",
            ))
            await session.commit()
            await _notify_operators_overbook(tval, arrival, departure, bid, guest)
            return 0

        res = Reservation(
            property_id=unit.id,
            check_in=arrival, check_out=departure,
            guest_name=guest, guest_phone=phone,
            guest_count=(b.get("numAdult") or 0) + (b.get("numChild") or 0) or None,
            status=ReservationStatus.CONFIRMED,
            source=src,
            total_amount=total_uzs,
            channel_booking_id=bid,
            note=note,
        )
        session.add(res)
        await session.commit()
        await session.refresh(res)
        session.add(ReservationEvent(
            reservation_id=res.id, actor_name="Beds24", action="created",
            detail=f"Импорт с канала: {unit.name_ru} · {arrival}→{departure} · {note}",
        ))
        await session.commit()
        await _notify_operators_new(res, unit.name_ru, src)
        return 1


async def _notify_operators_new(res, unit_name: str, src: ReservationSource):
    try:
        from db.enums import RESERVATION_SOURCE_LABELS
        from services.customer_notify import notify_operators_booking
        await notify_operators_booking(res, unit_name,
                                       RESERVATION_SOURCE_LABELS.get(src, src.value))
    except Exception as e:  # noqa: BLE001
        logger.warning("beds24 operator notify failed: %s", e)


async def _notify_operators_overbook(tval, arrival, departure, bid, guest):
    try:
        from services.customer_notify import notify_operators_booking
        fake = SimpleNamespace(id=0, check_in=arrival, check_out=departure,
                               guest_name=f"⚠️ ОВЕРБУКИНГ {tval}: {guest or '—'}",
                               guest_phone=f"Beds24 #{bid}")
        await notify_operators_booking(fake, f"⚠️ НЕТ СВОБОДНЫХ {tval}", "OTA overbooking")
    except Exception as e:  # noqa: BLE001
        logger.warning("beds24 overbook notify failed: %s", e)
