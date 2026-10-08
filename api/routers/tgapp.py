"""Telegram Mini App sign-in for operators (2026-10).

The «✍️ Оформить бронь» button on a /бронь card opens a Mini App of @balandda_bot
(t.me/balandda_bot/<short>?startapp=<draft token>) inside Telegram — no browser, no login
page. Telegram signs the launch data (initData) with the bot token; we verify that
signature, find the operator by their Telegram id among the calendar's staff, and hand
back the same session token the calendar login issues. Anyone else who opens the link
gets «нет доступа».
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from urllib.parse import parse_qsl

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth import create_session_token
from bot.config import settings
from db.database import get_session
from db.models import User

router = APIRouter()

# Staff who may create bookings from Telegram.
ALLOWED_ROLES = {"OWNER", "ADMIN", "OPERATOR", "RESORT_MANAGER"}
MAX_AGE = 24 * 3600


def verify_init_data(init_data: str, bot_token: str) -> dict | None:
    """Telegram WebApp initData check (HMAC-SHA256, key = HMAC("WebAppData", bot_token))."""
    if not init_data or not bot_token:
        return None
    pairs = dict(parse_qsl(init_data, keep_blank_values=True))
    given = pairs.pop("hash", None)
    if not given:
        return None
    check = "\n".join(f"{k}={v}" for k, v in sorted(pairs.items()))
    secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    calc = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(calc, given):
        return None
    try:
        if time.time() - int(pairs.get("auth_date", "0")) > MAX_AGE:
            return None
        user = json.loads(pairs.get("user") or "{}")
    except (ValueError, json.JSONDecodeError):
        return None
    return {"user": user, "start_param": pairs.get("start_param")}


class AuthInput(BaseModel):
    init_data: str


@router.post("/auth")
async def tgapp_auth(data: AuthInput, session: AsyncSession = Depends(get_session)):
    v = verify_init_data(data.init_data, settings.customer_bot_token)
    if not v or not v["user"].get("id"):
        raise HTTPException(status_code=401, detail="Не удалось проверить вход через Telegram")
    tid = int(v["user"]["id"])
    u = (await session.execute(select(User).where(User.telegram_id == tid))).scalar_one_or_none()
    role = getattr(getattr(u, "role", None), "value", getattr(u, "role", None)) if u else None
    if not u or not getattr(u, "is_active", True) or str(role) not in ALLOWED_ROLES:
        raise HTTPException(status_code=403, detail="Нет доступа: ваш Telegram не найден среди сотрудников календаря")
    return {
        "token": create_session_token(tid, str(role)),
        "user": {"telegram_id": tid, "full_name": u.full_name, "role": str(role)},
        "start_param": v.get("start_param"),
    }


# ───────────────────────── Guest booking (2026-10) ─────────────────────────
# The same Mini App (t.me/balandda_bot/book) in guest mode: anyone who opens it and is not
# staff, or whose start_param is "g" / "g_<draft token>". Guests pick dates + house type,
# we assign the cheapest free unit of that type, create the HOLD exactly like the chat
# wizard (bridge.self_book) and go straight to payment.

import re as _re
from datetime import date as _date, datetime as _dt, timedelta as _td, timezone as _tz

from sqlalchemy import func as _func

from db.enums import ReservationStatus
from db.models import Reservation, ReservationEvent

GUEST_ACTOR = "Клиент (Mini App)"
_PHONE_RE = _re.compile(r"\d")


def _guest(init_data: str) -> dict:
    v = verify_init_data(init_data, settings.customer_bot_token)
    if not v or not v["user"].get("id"):
        raise HTTPException(status_code=401, detail="Не удалось проверить вход через Telegram")
    return v


def _draft_token(start_param: str | None) -> str | None:
    sp = (start_param or "").strip()
    if sp.startswith("g_") and len(sp) > 2:
        tok = sp[2:]
        return tok if _re.fullmatch(r"[A-Za-z0-9_-]{8,40}", tok) else None
    return None


class GuestInit(BaseModel):
    init_data: str


@router.post("/guest/session")
async def guest_session(data: GuestInit):
    from services.customer_notify import crm_request
    v = _guest(data.init_data)
    draft = None
    tok = _draft_token(v.get("start_param"))
    if tok:
        st_, d = await crm_request("GET", f"/api/tg-draft/{tok}")
        if st_ == 200 and d.get("ok") and d.get("status") != "booked":
            draft = {k: d.get(k) for k in ("check_in", "check_out", "customer_name", "phone", "guests", "language")}
    return {"ok": True, "draft": draft, "user_id": v["user"]["id"]}


@router.post("/guest/expect-contact")
async def guest_expect_contact(data: GuestInit):
    """The guest is about to tap «share my number»: tell the CRM to file that contact
    silently instead of relaying it to operators as a live-chat message."""
    from services.customer_notify import crm_request
    v = _guest(data.init_data)
    await crm_request("POST", "/api/expect-contact", {"telegram_user_id": int(v["user"]["id"])}, timeout=5)
    return {"ok": True}


class GuestBook(BaseModel):
    init_data: str
    type: str
    check_in: _date
    check_out: _date
    guests: int | None = None
    name: str
    phone: str
    email: str | None = None
    lang: str | None = "ru"


@router.post("/guest/book")
async def guest_book(data: GuestBook, session: AsyncSession = Depends(get_session)):
    from api.routers.bridge import SelfBookData, _safe_email, self_book
    from api.routers.public import public_availability
    from services.customer_notify import crm_notify, crm_request
    from services.tg_pay import pay_message
    from services.voucher import load_voucher_data, norm_lang

    v = _guest(data.init_data)
    u = v["user"]
    tid = int(u["id"])
    lg = norm_lang(data.lang)
    name = (data.name or "").strip()[:120]
    phone = (data.phone or "").strip()[:40]
    if len(name) < 2:
        raise HTTPException(status_code=400, detail="name")
    if len(_PHONE_RE.findall(phone)) < 9:
        raise HTTPException(status_code=400, detail="phone")

    # Abuse guard: at most 3 unpaid holds per Telegram account in 3 hours.
    since = _dt.now(_tz.utc) - _td(hours=3)
    n_holds = (await session.execute(
        select(_func.count()).select_from(Reservation).where(
            Reservation.telegram_user_id == tid,
            Reservation.status == ReservationStatus.HOLD,
            Reservation.created_at >= since,
        )
    )).scalar() or 0
    if n_holds >= 3:
        raise HTTPException(status_code=429, detail="too_many")

    av = await public_availability(check_in=data.check_in, check_out=data.check_out,
                                   guests=max(1, data.guests or 1), session=session)
    if av.get("error"):
        raise HTTPException(status_code=409, detail=av["error"])
    units = [x for x in av["available_units"] if x["type"] == data.type]
    if not units:
        raise HTTPException(status_code=409, detail="unavailable")
    units.sort(key=lambda x: (x["price_total"] or 0))

    r = None
    for unit in units[:3]:   # a unit grabbed in the meantime → try the next one
        r = await self_book(SelfBookData(
            property_code=unit["code"], check_in=data.check_in, check_out=data.check_out,
            guests=data.guests, guest_name=name, guest_phone=phone,
            guest_email=_safe_email(data.email) if data.email else None,
            telegram_user_id=tid, telegram_username=u.get("username"), source="TELEGRAM",
        ), session=session, x_bridge_secret=settings.bridge_secret)
        if r.get("ok") or r.get("error") != "unavailable":
            break
    if not r or not r.get("ok"):
        raise HTTPException(status_code=409, detail=(r or {}).get("error") or "unavailable")

    bid = r["booking_id"]
    ev = (await session.execute(
        select(ReservationEvent).where(ReservationEvent.reservation_id == bid, ReservationEvent.action == "created")
    )).scalars().first()
    if ev:
        ev.actor_name = GUEST_ACTOR
        ev.detail = (ev.detail or "") + " · Telegram Mini App"
    await session.commit()

    tok = _draft_token(v.get("start_param"))
    total = float(r.get("total_amount") or 0)
    # CRM: bot-chat stats, the «Брони» operator card, and the /бронь draft (if any) → booked.
    await crm_request("POST", "/api/guest-booked", {
        "telegram_user_id": tid,
        "first_name": u.get("first_name"), "last_name": u.get("last_name"), "username": u.get("username"),
        "draft": tok, "booking_id": bid, "unit_name": r.get("unit_name"),
        "check_in": r.get("check_in"), "check_out": r.get("check_out"), "nights": r.get("nights"),
        "guest_name": name, "guest_phone": phone, "amount": total or None,
    }, timeout=15)

    # Payment request into the guest's chat (bot first; chimgan chat as fallback) —
    # the same message operators send with «💳 Счёт в Telegram».
    res = await session.get(Reservation, bid)
    vd = await load_voucher_data(session, res, lg)
    text, rows = pay_message(lg, vd)
    for row in rows:
        for b in row:
            if "/bridge/pay/" in b["url"]:
                b["url"] += f"?l={lg}&c=bot"
    sent = await crm_notify(tid, text, via="bot", buttons=rows) if rows else {"ok": False}
    session.add(ReservationEvent(
        reservation_id=bid, actor_name=GUEST_ACTOR, action="telegram",
        detail=("Счёт на оплату отправлен гостю в Telegram" if sent.get("ok")
                else f"Счёт на оплату в Telegram не отправлен: {sent.get('error')}"),
    ))
    await session.commit()

    urls = {b["url"].split("/bridge/pay/")[1].split("/")[1]: b["url"] for row in rows for b in row if "/bridge/pay/" in b["url"]}
    return {
        "ok": True,
        "booking_id": bid,
        "unit_name": vd.get("unit") or r.get("unit_name"),
        "check_in": r["check_in"], "check_out": r["check_out"], "nights": r["nights"],
        "total_amount": total or None,
        "deposit_amount": round(total * 0.2) if total else None,
        "full_amount": round(total * 0.95) if total else None,
        "pay_deposit_url": urls.get("deposit"),
        "pay_full_url": urls.get("full"),
        "message_sent": bool(sent.get("ok")),
    }
