"""Server-side ad conversions (2026-10).

Most bookings no longer happen on the website: guests click through to Telegram /
Instagram and book in a chat, the bot or the Mini App, and pay by an operator's link, in
cash or by transfer. The website reports its own Lead/Purchase (book.php / octopay.php);
everything else was invisible to the ad platforms. This module fills that gap:

  Lead      — a booking made from a chat (Telegram / Instagram / an operator's /бронь in a
              @balandda_chimgan chat). event_id "lead-<reservation id>".
  Purchase  — the FIRST money received for a booking (not OTA): always for Octo card
              payments; for cash / transfer / terminal only when the guest is ad-origin
              (we hold a click id or paid UTM for them). event_id "paid-<reservation id>" —
              the same id octopay.php uses, so Meta counts one if both ever fire.

Every event is written to the ad_conversions ledger. Meta gets it right away through the
Conversions API (dataset settings.meta_dataset_id, token settings.meta_capi_token; with
settings.meta_test_event_code set, events go to Test Events only). Google Ads and Yandex
Metrika are fed from the same ledger as offline-conversion CSV files
(/api/v1/ad-conversions/export) until the API upload is wired.

A scan runs every 5 minutes from the bot scheduler (run_scan); it is idempotent — the
ledger has one row per (reservation, event).
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from datetime import date, datetime, timedelta, timezone

import aiohttp
from sqlalchemy import and_, exists, func, select
from sqlalchemy.exc import IntegrityError

from bot.config import settings
from db.database import async_session
from db.enums import ReservationSource, ReservationStatus
from db.models import AdConversion, IncomeEntry, Prepayment, Property, Reservation, ReservationAds

log = logging.getLogger(__name__)

OTA = {ReservationSource.BOOKING_COM, ReservationSource.AIRBNB, ReservationSource.TRIP_COM}
CHAT = {ReservationSource.TELEGRAM, ReservationSource.INSTAGRAM}
SKIP_STATUS = {ReservationStatus.BLOCKED}
CLICK_IDS = ("gclid", "gbraid", "wbraid", "yclid", "fbclid", "fbc")
KEEP_KEYS = CLICK_IDS + ("fbp", "ym_cid", "ga_cid", "utm_source", "utm_medium", "utm_campaign",
                         "utm_content", "utm_term", "landing", "code", "ts")
PAID_MEDIUM = re.compile(r"^(cpc|ppc|paid|paidsocial|paid_social|cpm|cpa|display|ads?)$", re.I)
META_MAX_AGE = timedelta(days=7) - timedelta(minutes=30)   # Meta rejects events older than 7 days


def _since() -> datetime:
    try:
        d = date.fromisoformat(settings.ad_conv_since)
    except ValueError:
        d = date(2026, 10, 8)
    return datetime(d.year, d.month, d.day, tzinfo=timezone.utc)


def _sha(v: str) -> str:
    return hashlib.sha256(v.encode()).hexdigest()


def norm_phone(p: str | None) -> str | None:
    d = re.sub(r"\D", "", p or "")
    if len(d) == 9:              # local 90 123 45 67 → 998901234567
        d = "998" + d
    return d if len(d) >= 10 else None


def clean_ads(raw: dict | None) -> dict:
    out = {}
    for k in KEEP_KEYS:
        v = (raw or {}).get(k)
        if v not in (None, ""):
            out[k] = str(v)[:300]
    return out


def is_ad_origin(ads: dict | None) -> bool:
    ads = ads or {}
    if any(ads.get(k) for k in CLICK_IDS):
        return True
    return bool(PAID_MEDIUM.match(ads.get("utm_medium") or ""))


async def _crm_attribution(tid: int | None, phone: str | None) -> dict:
    """Click ids the CRM matched to this guest (Telegram click code on the site → /start,
    first chimgan message or Mini App start_param). Empty until that bridge knows them."""
    if not tid and not phone:
        return {}
    from services.customer_notify import crm_request
    q = f"telegram_user_id={int(tid)}" if tid else f"phone={norm_phone(phone) or ''}"
    st, d = await crm_request("GET", f"/api/attribution?{q}", timeout=8)
    return clean_ads(d.get("ads")) if st == 200 and d.get("ok") else {}


async def ads_for(session, res: Reservation) -> dict:
    row = await session.get(ReservationAds, res.id)
    if row and row.data:
        return dict(row.data)
    ads = await _crm_attribution(res.telegram_user_id, res.guest_phone)
    if ads:
        if row:
            row.data, row.origin = ads, "crm"
        else:
            session.add(ReservationAds(reservation_id=res.id, data=ads, origin="crm"))
    return ads


def _user_data(res: Reservation, ads: dict) -> dict:
    ud: dict = {"country": [_sha("uz")]}
    ph = norm_phone(res.guest_phone)
    if ph:
        ud["ph"] = [_sha(ph)]
    if res.guest_email and "@" in res.guest_email:
        ud["em"] = [_sha(res.guest_email.strip().lower())]
    if res.guest_name:
        parts = res.guest_name.strip().lower().split()
        if parts:
            ud["fn"] = [_sha(parts[0])]
        if len(parts) > 1:
            ud["ln"] = [_sha(parts[-1])]
    if res.telegram_user_id:
        ud["external_id"] = [_sha(f"tg:{res.telegram_user_id}")]
    if ads.get("fbp"):
        ud["fbp"] = ads["fbp"]
    if ads.get("fbc"):
        ud["fbc"] = ads["fbc"]
    elif ads.get("fbclid"):
        try:
            ms = int(float(ads.get("ts") or 0) * (1000 if float(ads.get("ts") or 0) < 1e12 else 1))
        except ValueError:
            ms = 0
        ud["fbc"] = f"fb.1.{ms or int(res.created_at.timestamp() * 1000)}.{ads['fbclid']}"
    return ud


async def send_meta(events: list[dict]) -> tuple[str, str]:
    """POST events to the Meta Conversions API → (status, response text)."""
    if not settings.meta_capi_token:
        return "pending", "no token"
    body: dict = {"data": events}
    if settings.meta_test_event_code:
        body["test_event_code"] = settings.meta_test_event_code
    url = f"https://graph.facebook.com/v19.0/{settings.meta_dataset_id}/events"
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(url, params={"access_token": settings.meta_capi_token}, json=body,
                              timeout=aiohttp.ClientTimeout(total=20)) as r:
                txt = (await r.text())[:900]
                if r.status == 200:
                    return ("test" if settings.meta_test_event_code else "sent"), txt
                return "error", f"HTTP {r.status}: {txt}"
    except Exception as e:  # network — retried on the next scan
        return "pending", f"network: {e!r}"[:300]


def _action_source(conv: AdConversion, res: Reservation) -> str:
    if conv.event_name == "Lead":
        return "chat"
    if conv.pay_kind == "offline":
        return "physical_store"          # cash / transfer / terminal at reception
    return "chat" if (res.source in CHAT or res.telegram_user_id) else "system_generated"


def _meta_event(conv: AdConversion, res: Reservation, unit: str, ads: dict) -> dict:
    return {
        "event_name": conv.event_name,
        "event_time": int(conv.event_time.timestamp()),
        "event_id": conv.event_id,
        "action_source": _action_source(conv, res),
        "user_data": _user_data(res, ads),
        "custom_data": {
            "currency": conv.currency,
            "value": float(conv.value or 0),
            "content_name": unit,
            "content_category": "accommodation",
            "order_id": str(res.id),
            "num_items": 1,
        },
    }


async def _record(session, res: Reservation, event: str, when: datetime, value, pay_kind: str | None,
                  meta_status: str = "pending") -> AdConversion | None:
    ads = await ads_for(session, res)
    conv = AdConversion(
        reservation_id=res.id, event_name=event,
        event_id=f"{'lead' if event == 'Lead' else 'paid'}-{res.id}",
        event_time=when, value=value, currency="UZS",
        source=res.source.value if hasattr(res.source, "value") else str(res.source),
        pay_kind=pay_kind, ad_origin=is_ad_origin(ads), ads=ads or None, meta_status=meta_status,
    )
    if event == "Purchase" and pay_kind == "offline" and not conv.ad_origin:
        conv.meta_status = "skip_not_ad"     # cash / transfer from a guest we can't tie to an ad
    if event == "Purchase" and pay_kind == "octo_site":
        conv.meta_status = "skip_site"       # octopay.php already reported it (same event_id)
    try:
        async with session.begin_nested():   # savepoint: a duplicate never undoes the others
            session.add(conv)
    except IntegrityError:
        return None
    return conv


async def collect(session, limit: int = 100) -> dict:
    """Add ledger rows for new chat bookings (Lead) and first payments (Purchase)."""
    since = _since()
    now = datetime.now(timezone.utc)
    added = {"Lead": 0, "Purchase": 0}

    # Lead — chat bookings (bot, Mini App, Instagram) and operator bookings tied to a Telegram chat.
    has_lead = exists().where(and_(AdConversion.reservation_id == Reservation.id, AdConversion.event_name == "Lead"))
    leads = (await session.execute(
        select(Reservation).where(
            Reservation.created_at >= since,
            Reservation.created_at <= now - timedelta(minutes=2),
            Reservation.status.notin_(SKIP_STATUS),
            (Reservation.source.in_(CHAT))
            | (Reservation.source.in_([ReservationSource.MANUAL, ReservationSource.PHONE])
               & Reservation.telegram_user_id.isnot(None)),
            ~has_lead,
        ).order_by(Reservation.id).limit(limit)
    )).scalars().all()
    for res in leads:
        if await _record(session, res, "Lead", res.created_at, res.total_amount, None):
            added["Lead"] += 1
    await session.commit()

    # Purchase — the first money in, on any non-OTA booking.
    first = (
        select(IncomeEntry.reservation_id.label("rid"), func.min(IncomeEntry.id).label("iid"))
        .where(IncomeEntry.reservation_id.isnot(None), IncomeEntry.amount > 0)
        .group_by(IncomeEntry.reservation_id).subquery()
    )
    has_buy = exists().where(and_(AdConversion.reservation_id == Reservation.id, AdConversion.event_name == "Purchase"))
    rows = (await session.execute(
        select(Reservation, IncomeEntry)
        .join(first, first.c.rid == Reservation.id)
        .join(IncomeEntry, IncomeEntry.id == first.c.iid)
        .where(
            IncomeEntry.created_at >= since,
            Reservation.source.notin_(OTA),
            Reservation.status.notin_(SKIP_STATUS),
            ~has_buy,
        ).order_by(IncomeEntry.id).limit(limit)
    )).all()
    for res, inc in rows:
        note = (await session.execute(
            select(Prepayment.note).where(Prepayment.income_entry_id == inc.id)
        )).scalar_one_or_none() or ""
        if "Octo" in note:
            pay_kind = "octo_site" if "(сайт)" in note else "octo"
        else:
            pay_kind = "offline"
        value = float(res.total_amount or 0) or float(inc.amount or 0)
        if await _record(session, res, "Purchase", inc.created_at or now, value, pay_kind):
            added["Purchase"] += 1
    await session.commit()
    return added


async def push_meta(session, limit: int = 100) -> dict:
    """Send pending ledger rows to Meta (batched)."""
    now = datetime.now(timezone.utc)
    pend = (await session.execute(
        select(AdConversion).where(AdConversion.meta_status == "pending").order_by(AdConversion.id).limit(limit)
    )).scalars().all()
    if not pend:
        return {"sent": 0}
    if not settings.meta_capi_token:
        return {"sent": 0, "waiting": len(pend), "note": "no META_CAPI_TOKEN"}
    batch, rows = [], []
    for conv in pend:
        if now - conv.event_time > META_MAX_AGE:
            conv.meta_status, conv.meta_response = "skip_old", "older than 7 days"
            continue
        res = await session.get(Reservation, conv.reservation_id)
        if not res:
            conv.meta_status = "skip_gone"
            continue
        prop = await session.get(Property, res.property_id)
        batch.append(_meta_event(conv, res, prop.name_ru if prop else "", conv.ads or {}))
        rows.append(conv)
    status, resp = ("pending", "")
    if batch:
        status, resp = await send_meta(batch)
        for conv in rows:
            conv.meta_status, conv.meta_response = status, resp
            if status in ("sent", "test"):
                conv.meta_sent_at = now
    await session.commit()
    return {"sent": len(rows) if status in ("sent", "test") else 0, "status": status}


async def run_scan() -> dict:
    """Scheduler entry point (every 5 minutes)."""
    try:
        async with async_session() as session:
            added = await collect(session)
            pushed = await push_meta(session)
        if added["Lead"] or added["Purchase"] or pushed.get("sent"):
            log.info("ad conversions: added %s, meta %s", added, pushed)
        return {"added": added, "meta": pushed}
    except Exception:
        log.exception("ad conversions scan failed")
        return {"error": True}


# ---------- offline-conversion files for Google Ads / Yandex Metrika ----------

def _tz_time(dt: datetime) -> str:
    t = dt.astimezone(timezone(timedelta(hours=5)))
    return t.strftime("%Y-%m-%d %H:%M:%S+0500")


def google_csv(rows: list[AdConversion]) -> str:
    """Google Ads «Upload clicks» template (one click id per row)."""
    import csv, io
    buf = io.StringIO()
    buf.write("Parameters:TimeZone=Asia/Tashkent\n")
    w = csv.writer(buf)
    w.writerow(["Google Click ID", "GBRAID", "WBRAID", "Conversion Name", "Conversion Time",
                "Conversion Value", "Conversion Currency", "Order ID"])
    for c in rows:
        a = c.ads or {}
        if not (a.get("gclid") or a.get("gbraid") or a.get("wbraid")):
            continue
        name = settings.google_conv_purchase if c.event_name == "Purchase" else settings.google_conv_lead
        w.writerow([a.get("gclid", ""), "" if a.get("gclid") else a.get("gbraid", ""),
                    "" if a.get("gclid") or a.get("gbraid") else a.get("wbraid", ""),
                    name, _tz_time(c.event_time).replace("+0500", ""), int(float(c.value or 0)), c.currency, c.event_id])
    return buf.getvalue()


def yandex_csv(rows: list[AdConversion]) -> str:
    """Yandex Metrika offline conversions: by ClientId (_ym_uid) or, failing that, yclid."""
    import csv, io
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["ClientId", "Yclid", "Target", "DateTime", "Price", "Currency"])
    for c in rows:
        a = c.ads or {}
        if not (a.get("ym_cid") or a.get("yclid")):
            continue
        target = settings.yandex_target_purchase if c.event_name == "Purchase" else settings.yandex_target_lead
        w.writerow([a.get("ym_cid", ""), "" if a.get("ym_cid") else a.get("yclid", ""), target,
                    int(c.event_time.timestamp()), int(float(c.value or 0)), "UZS"])
    return buf.getvalue()
