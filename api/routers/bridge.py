"""Bridge endpoints called by the CRM (@balandda_bot) — secret-authed.

When a customer taps the connect deep-link, the CRM bot reports their Telegram id
here; we attach it to the booking and return the booking-received text for the CRM
to reply with.
"""

import asyncio
import re
import secrets
from datetime import date, datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from api.routers.public import _stay_total
from services.octo_service import octo_prepare, octo_status
from api.routers.reservations import _get_or_create_report
from bot.config import settings
from db.booking_rules import validate_stay
from db.database import get_session
from db.enums import (
    BusinessUnit,
    PaymentMethod,
    PrepaymentStatus,
    ReservationSource,
    ReservationStatus,
    WalletTransactionStatus,
    WalletTransactionType,
)
from db.hold_timing import add_working_minutes
from db.models import IncomeEntry, Prepayment, Property, Reservation, ReservationEvent, User, WalletTransaction
from services.beds24 import kick as beds24_kick  # OTA availability push
from services.mailer import send_email
from services.voucher import build_email, build_voucher_pdf, checkin_times, norm_lang
from services.customer_notify import (
    booking_payment_text,
    booking_received_text,
    get_prepayment_instructions,
    notify_operators_booking,
    send_customer_message,
)
from sqlalchemy import func

router = APIRouter()


class ConnectData(BaseModel):
    token: str
    telegram_user_id: int
    telegram_username: str | None = None


def _check_secret(secret: str | None):
    if not settings.bridge_secret or secret != settings.bridge_secret:
        raise HTTPException(status_code=401, detail="unauthorized")


@router.post("/telegram-connect")
async def telegram_connect(
    data: ConnectData,
    session: AsyncSession = Depends(get_session),
    x_bridge_secret: str | None = Header(default=None),
):
    _check_secret(x_bridge_secret)
    res = (
        await session.execute(select(Reservation).where(Reservation.connect_token == data.token))
    ).scalar_one_or_none()
    if not res:
        raise HTTPException(status_code=404, detail="booking not found")

    res.telegram_user_id = data.telegram_user_id
    if data.telegram_username:
        res.telegram_username = data.telegram_username.lstrip("@")
    already = res.booking_notified_at is not None
    if not already:
        res.booking_notified_at = datetime.now(timezone.utc)
    prop = await session.get(Property, res.property_id)
    await session.commit()

    prepay_text = await get_prepayment_instructions()
    return {
        "ok": True,
        "already": already,
        "message": booking_received_text(res, prop.name_ru if prop else "", prepay_text),
    }


class SelfBookData(BaseModel):
    property_code: str
    check_in: date
    check_out: date
    guests: int | None = None
    guest_name: str | None = None
    guest_phone: str | None = None
    guest_email: str | None = None
    # Optional: Instagram customers self-book too, and they have no Telegram identity.
    telegram_user_id: int | None = None
    telegram_username: str | None = None
    # "TELEGRAM" (default) | "INSTAGRAM" — so the calendar shows where the booking came from.
    source: str | None = None


@router.post("/self-book")
async def self_book(
    data: SelfBookData,
    session: AsyncSession = Depends(get_session),
    x_bridge_secret: str | None = Header(default=None),
):
    """Customer self-booking from @balandda_bot: create an unpaid HOLD on the chosen unit
    (with the customer's Telegram id) and return the booking-received message to reply with.
    The DB overlap constraint guarantees no double-booking → returns unavailable on conflict."""
    _check_secret(x_bridge_secret)
    if data.check_out <= data.check_in:
        raise HTTPException(status_code=400, detail="check_out must be after check_in")
    prop = (
        await session.execute(
            select(Property).where(Property.code == data.property_code, Property.is_active.is_(True))
        )
    ).scalar_one_or_none()
    if not prop:
        raise HTTPException(status_code=404, detail="unit not found")

    # Booking date rules: no past check-ins, sales window, admin-blocked dates.
    date_err = await validate_stay(session, prop.id, data.check_in, data.check_out)
    if date_err:
        return {"ok": False, "error": date_err}

    now = datetime.now(timezone.utc)
    total = await _stay_total(session, prop, data.check_in, data.check_out)
    res = Reservation(
        property_id=prop.id,
        check_in=data.check_in,
        check_out=data.check_out,
        guest_name=data.guest_name,
        guest_phone=data.guest_phone,
        guest_email=data.guest_email,
        guest_count=data.guests,
        telegram_user_id=data.telegram_user_id,
        telegram_username=(data.telegram_username.lstrip("@") if data.telegram_username else None),
        status=ReservationStatus.HOLD,
        source=(
            ReservationSource.INSTAGRAM
            if (data.source or "").upper() == "INSTAGRAM"
            else ReservationSource.TELEGRAM
        ),
        total_amount=total or None,
        hold_warn_at=add_working_minutes(now, 30),
        hold_expires_at=add_working_minutes(now, 60),
        booking_notified_at=now,
    )
    session.add(res)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        return {"ok": False, "error": "unavailable"}
    await session.refresh(res)
    session.add(ReservationEvent(
        reservation_id=res.id, actor_name="Клиент (бот)", action="created",
        detail=f"Онлайн-бронь: {prop.name_ru} · {data.check_in}→{data.check_out}",
    ))
    await session.commit()
    beds24_kick()

    prepay_text = await get_prepayment_instructions()
    return {
        "ok": True,
        "booking_id": res.id,
        "unit_name": prop.name_ru,
        "check_in": data.check_in.isoformat(),
        "check_out": data.check_out.isoformat(),
        "nights": (data.check_out - data.check_in).days,
        "total_amount": float(total) if total else None,
        "prepay_amount": int(round((total or 0) * 0.2)) or None,
        "guest_name": data.guest_name,
        "message": booking_received_text(res, prop.name_ru, prepay_text),
    }


class WebBookData(BaseModel):
    property_code: str
    check_in: date
    check_out: date
    guests: int | None = None
    guest_name: str
    guest_phone: str
    guest_email: str | None = None


@router.post("/web-book")
async def web_book(
    data: WebBookData,
    session: AsyncSession = Depends(get_session),
    x_bridge_secret: str | None = Header(default=None),
):
    """Self-booking from the balandda.uz website (no Telegram id yet).

    Creates an unpaid HOLD (source=DIRECT) on the chosen unit and returns a
    connect_token so the site can offer a "Continue in Telegram" deep-link
    (@balandda_bot?start=connect_<token>) that later attaches the customer's chat.
    The DB overlap constraint prevents double-booking → returns unavailable on conflict.
    """
    _check_secret(x_bridge_secret)
    if data.check_out <= data.check_in:
        raise HTTPException(status_code=400, detail="check_out must be after check_in")
    prop = (
        await session.execute(
            select(Property).where(Property.code == data.property_code, Property.is_active.is_(True))
        )
    ).scalar_one_or_none()
    if not prop:
        raise HTTPException(status_code=404, detail="unit not found")

    # Booking date rules: no past check-ins, sales window, admin-blocked dates.
    date_err = await validate_stay(session, prop.id, data.check_in, data.check_out)
    if date_err:
        return {"ok": False, "error": date_err}

    now = datetime.now(timezone.utc)
    total = await _stay_total(session, prop, data.check_in, data.check_out)
    res = Reservation(
        property_id=prop.id,
        check_in=data.check_in,
        check_out=data.check_out,
        guest_name=data.guest_name,
        guest_phone=data.guest_phone,
        guest_count=data.guests,
        status=ReservationStatus.HOLD,
        source=ReservationSource.DIRECT,
        total_amount=total or None,
        connect_token=secrets.token_urlsafe(12)[:16],
        hold_warn_at=add_working_minutes(now, 30),
        hold_expires_at=add_working_minutes(now, 60),
        booking_notified_at=now,
    )
    session.add(res)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        return {"ok": False, "error": "unavailable"}
    await session.refresh(res)
    session.add(ReservationEvent(
        reservation_id=res.id, actor_name="Клиент (сайт)", action="created",
        detail=f"Онлайн-бронь (сайт): {prop.name_ru} · {data.check_in}→{data.check_out}",
    ))
    await session.commit()
    beds24_kick()

    # Announce to the operators' Брони topic (website bookings have no bot to do it).
    await notify_operators_booking(res, prop.name_ru, "сайт")

    prepay_text = await get_prepayment_instructions()
    prepay_amount = int(round((total or 0) * 0.2))
    connect_url = f"https://t.me/{settings.customer_bot_username}?start=connect_{res.connect_token}"
    return {
        "ok": True,
        "booking_id": res.id,
        "unit_name": prop.name_ru,
        "check_in": data.check_in.isoformat(),
        "check_out": data.check_out.isoformat(),
        "nights": (data.check_out - data.check_in).days,
        "total_amount": total,
        "prepay_amount": prepay_amount,
        "prepay_text": prepay_text,
        "connect_token": res.connect_token,
        "connect_url": connect_url,
        "guest_name": data.guest_name,
        "message": booking_received_text(res, prop.name_ru, prepay_text),
    }


# ── Sklad purchases (balandda-tk mini-app) — cash purchase wallet deduction ──


class PurchaseExpenseData(BaseModel):
    telegram_id: int          # buyer (Азизов 548813671 / Пулатов 1271114713)
    amount: float             # approved purchase total, UZS
    pending_id: str           # balandda-tk pending record id — idempotency key
    doc_num: str | None = None        # iiko invoice number (e.g. "0402")
    description: str | None = None    # short item summary
    purchase_date: str | None = None  # informational


@router.post("/purchase-expense")
async def purchase_expense(
    data: PurchaseExpenseData,
    session: AsyncSession = Depends(get_session),
    x_bridge_secret: str | None = Header(default=None),
):
    """Called by balandda-tk when an approved закуп was paid in CASH:
    deducts the amount from the buyer's cash wallet (type=PURCHASE).

    Idempotent: the pending_id marker in the note guards against retries.
    Returns the buyer's remaining wallet balance so the mini-app / DM can show it.
    """
    _check_secret(x_bridge_secret)

    if data.amount <= 0:
        raise HTTPException(status_code=400, detail="amount must be positive")

    marker = f"[sklad:{data.pending_id}]"
    existing = (
        await session.execute(
            select(WalletTransaction.id).where(WalletTransaction.note.like(f"%{marker}%"))
        )
    ).first()

    if not existing:
        doc_part = f" №{data.doc_num}" if data.doc_num else ""
        desc_part = f" — {data.description}" if data.description else ""
        session.add(WalletTransaction(
            sender_telegram_id=data.telegram_id,
            amount=Decimal(round(data.amount)),
            transaction_type=WalletTransactionType.PURCHASE,
            status=WalletTransactionStatus.COMPLETED,
            note=f"Закуп iiko{doc_part}{desc_part} {marker}",
            business_unit=BusinessUnit.RESTAURANT,
        ))
        await session.commit()

    # Remaining balance (same logic as the wallets router)
    from api.routers.wallets import _calculate_balance
    balance = await _calculate_balance(session, data.telegram_id)

    buyer_name = (
        await session.execute(select(User.full_name).where(User.telegram_id == data.telegram_id))
    ).scalar_one_or_none()

    return {
        "ok": True,
        "duplicate": bool(existing),
        "telegram_id": data.telegram_id,
        "buyer_name": buyer_name,
        "balance": balance,
    }


# ── Online payment from the website (Octo internet-acquiring) ──


class BridgePaymentData(BaseModel):
    booking_id: int
    amount: float
    provider: str = "OCTO"            # informational
    provider_uuid: str | None = None  # octo_payment_UUID — idempotency key
    card_mask: str | None = None      # e.g. 561468****4042
    card_vendor: str | None = None    # uzcard / humo / visa / mastercard
    guest_email: str | None = None    # for the confirmation e-mail + PDF voucher
    guest_lang: str | None = None     # ru / uz / en / zh (zh -> en)
    channel_label: str = "сайт"       # "сайт" | "бот" — for the operator messages


@router.post("/payment")
async def bridge_payment(
    data: BridgePaymentData,
    session: AsyncSession = Depends(get_session),
    x_bridge_secret: str | None = Header(default=None),
):
    """Card payment received by the website via Octo internet-acquiring.

    Mirrors the calendar's accept_payment flow: records the sum as income in
    today's report (owned by settings.octo_operator_tg), mirrors it into the
    Prepayment ledger, flips an unpaid HOLD to CONFIRMED (stops the expiry
    countdown), logs an event, announces to the operators' topic and messages
    the guest if their Telegram is connected. Idempotent by provider_uuid —
    the site calls this from both the webhook and the return-page check.
    """
    _check_secret(x_bridge_secret)
    res = await session.get(Reservation, data.booking_id)
    if not res:
        raise HTTPException(status_code=404, detail="booking not found")
    amt = round(float(data.amount or 0))
    if amt <= 0:
        raise HTTPException(status_code=400, detail="amount must be positive")

    # Idempotency: one ledger row per Octo payment UUID.
    if data.provider_uuid:
        dup = (
            await session.execute(
                select(Prepayment).where(
                    Prepayment.reservation_id == res.id,
                    Prepayment.note.ilike(f"%{data.provider_uuid}%"),
                )
            )
        ).scalars().first()
        if dup:
            return {"ok": True, "already": True, "booking_id": res.id, "status": res.status.value}

    operator = settings.octo_operator_tg
    prop = await session.get(Property, res.property_id)
    business_unit = prop.business_unit if prop and prop.business_unit else BusinessUnit.RESORT
    report = await _get_or_create_report(session, operator, business_unit)

    nights = (res.check_out - res.check_in).days or 1
    income = IncomeEntry(
        report_id=report.id, property_id=res.property_id, reservation_id=res.id,
        payment_method=PaymentMethod.CARD_TRANSFER, amount=amt, num_days=nights,
    )
    session.add(income)
    await session.flush()
    report.total_income = (report.total_income or 0) + amt

    note = f"Octo интернет-эквайринг ({data.channel_label})"
    if data.card_mask:
        note += f" · карта {data.card_mask}"
    if data.card_vendor:
        note += f" ({data.card_vendor})"
    if data.provider_uuid:
        note += f" · {data.provider_uuid}"
    session.add(Prepayment(
        guest_name=res.guest_name or "—", property_id=res.property_id,
        check_in_date=res.check_in, check_out_date=res.check_out,
        amount=amt, payment_method=PaymentMethod.CARD_TRANSFER.value,
        status=PrepaymentStatus.CONFIRMED,
        operator_telegram_id=operator, reservation_id=res.id,
        income_entry_id=income.id, settled_in_report_id=report.id, note=note,
    ))

    # First payment secures the booking: HOLD (red) -> CONFIRMED, stop the countdown.
    if res.status == ReservationStatus.HOLD:
        res.status = ReservationStatus.CONFIRMED
        res.hold_warn_at = None
        res.hold_expires_at = None
        res.hold_warned_at = None

    session.add(ReservationEvent(
        reservation_id=res.id, actor_name=f"Octo ({data.channel_label})", action="payment",
        detail=f"Онлайн-оплата картой: +{amt} сум · {note}",
    ))
    await session.commit()

    # Operators' topic + guest message — best-effort, never fail the payment.
    label = f"{data.channel_label} · 💳 ОПЛАЧЕНО {amt:,} сум (Octo)".replace(",", " ")
    try:
        await notify_operators_booking(res, prop.name_ru if prop else "", label)
    except Exception:
        pass
    if res.telegram_user_id:
        try:
            paid_sum = (
                await session.execute(
                    select(func.coalesce(func.sum(IncomeEntry.amount), 0)).where(
                        IncomeEntry.reservation_id == res.id
                    )
                )
            ).scalar() or 0
            total_amt = float(res.total_amount) if res.total_amount is not None else float(paid_sum)
            await send_customer_message(
                res.telegram_user_id,
                booking_payment_text(res, prop.name_ru if prop else "", amt, float(paid_sum), total_amt),
            )
        except Exception:
            pass

    # Confirmation e-mail with the PDF voucher — best-effort, never fails the payment.
    if data.guest_email and "@" in data.guest_email:
        try:
            t_in, t_out = checkin_times(prop.property_type.value if prop and prop.property_type else None)
            lang = norm_lang(data.guest_lang)
            vd = {
                "booking_id": res.id,
                "guest_name": res.guest_name,
                "unit": prop.name_ru if prop else "",
                "check_in": res.check_in.isoformat(),
                "check_out": res.check_out.isoformat(),
                "guests": res.guest_count,
                "nights": (res.check_out - res.check_in).days,
                "paid_amount": amt,
                "paid_card": data.card_mask,
                "total_amount": float(res.total_amount) if res.total_amount is not None else None,
                "t_in": t_in, "t_out": t_out,
            }
            subject, body = build_email(lang, vd)
            pdf = build_voucher_pdf(lang, vd)
            await asyncio.to_thread(
                send_email, data.guest_email, subject, body,
                f"balandda-voucher-{res.id}.pdf", pdf,
            )
        except Exception:
            pass

    return {"ok": True, "booking_id": res.id, "status": res.status.value, "amount": amt}


# ── Pay links for bookings made in the bots (Telegram + Instagram) ──
#
# The website creates its Octo payment inside book.php at booking time. The bots
# create the booking first (self-book above) and ask for money afterwards, so they
# need a way to start a payment for a booking that already exists. Same Octo shop,
# same money flow, same /payment bookkeeping — only the entry point is new.
#
# The booking id is carried inside our own shop_transaction_id ("BOT-<id>-<rand>"),
# so no extra table is needed to map a payment back to its booking.

IG_DIRECT_URL = "https://ig.me/m/balandda_chimgan"


class PayLinkData(BaseModel):
    booking_id: int
    kind: str = "full"                 # "full" | "deposit" (20%)
    lang: str | None = "ru"
    channel: str | None = "telegram"   # where to send the guest back after paying


@router.post("/pay-link")
async def pay_link(
    data: PayLinkData,
    session: AsyncSession = Depends(get_session),
    x_bridge_secret: str | None = Header(default=None),
):
    """Start an Octo payment for an existing bot booking and return its pay page."""
    _check_secret(x_bridge_secret)
    res = await session.get(Reservation, data.booking_id)
    if not res:
        raise HTTPException(status_code=404, detail="booking not found")
    if res.status not in (ReservationStatus.HOLD, ReservationStatus.CONFIRMED):
        return {"ok": False, "error": "not_payable"}
    prop = await session.get(Property, res.property_id)
    total = float(res.total_amount or 0)
    if total <= 0 and prop:
        total = float(await _stay_total(session, prop, res.check_in, res.check_out) or 0)
    amount = round(total) if data.kind != "deposit" else round(total * 0.2)
    if amount <= 0:
        return {"ok": False, "error": "no_amount"}

    tid = f"BOT-{res.id}-{secrets.token_hex(3)}"
    unit = prop.name_ru if prop else ""
    back = (
        IG_DIRECT_URL
        if (data.channel or "").lower() == "instagram"
        else f"https://t.me/{settings.customer_bot_username}"
    )
    url, uuid, msg = await octo_prepare(
        shop_transaction_id=tid,
        total_sum=amount,
        description=f"Оплата брони #{res.id} — {unit}, {res.check_in} → {res.check_out}",
        return_url=back,
        notify_url="https://analytics.berdiev.uz/api/v1/bridge/octo-notify",
        language=(data.lang or "ru"),
    )
    if not url:
        return {"ok": False, "error": msg}
    session.add(ReservationEvent(
        reservation_id=res.id, actor_name="Клиент (бот)", action="pay_link",
        detail=f"Ссылка на оплату {amount} сум ({data.kind}) · {tid}",
    ))
    await session.commit()
    return {"ok": True, "pay_url": url, "amount": amount, "kind": data.kind,
            "tid": tid, "provider_uuid": uuid}


@router.post("/octo-notify")
async def octo_notify(
    payload: dict,
    session: AsyncSession = Depends(get_session),
):
    """Octo's webhook for bot payments (public by design — Octo sends no auth).

    Nothing in the request body is trusted: we re-fetch the payment from Octo by
    our own transaction id and only then book the money, exactly as octopay.php
    does for the website. Applying it goes through /payment, so bot payments get
    the identical ledger row, HOLD→CONFIRMED flip, voucher and notifications.
    """
    tid = str((payload or {}).get("shop_transaction_id") or "").strip()
    if not (tid.startswith("BOT-") or tid.startswith("CAL-")):
        return {"ok": True, "ignored": "not ours"}
    d = await octo_status(tid)
    if not d:
        return {"ok": True, "ignored": "octo unreachable"}
    if str(d.get("status") or "") != "succeeded":
        return {"ok": True, "status": d.get("status")}
    try:
        booking_id = int(tid.split("-")[1])
    except (IndexError, ValueError):
        return {"ok": True, "ignored": "unparsable tid"}
    res = await session.get(Reservation, booking_id)
    if not res:
        return {"ok": True, "ignored": "booking gone"}

    amount = float(d.get("total_sum") or 0)
    channel = "календарь" if tid.startswith("CAL-") else "бот"
    if tid.startswith("CAL-"):
        # A calendar link may be in USD (OTA virtual cards). The soum sum to book
        # was fixed at link creation and lives in the pay_link event for this tid.
        ev = (
            await session.execute(
                select(ReservationEvent)
                .where(
                    ReservationEvent.reservation_id == booking_id,
                    ReservationEvent.action == "pay_link",
                    ReservationEvent.detail.ilike(f"%{tid}%"),
                )
                .order_by(ReservationEvent.id.desc())
            )
        ).scalars().first()
        if ev and "USD" in (ev.detail or ""):
            usd = amount
            m_uzs = re.search(r"к учёту (\d+) сум", ev.detail or "")
            if m_uzs:
                amount = float(m_uzs.group(1))
            channel = f"календарь · ${usd:.2f}"

    return await bridge_payment(
        BridgePaymentData(
            booking_id=booking_id,
            amount=amount,
            provider_uuid=d.get("octo_payment_UUID"),
            card_mask=d.get("maskedPan"),
            card_vendor=d.get("card_vendor"),
            guest_email=res.guest_email,
            guest_lang=None,
            channel_label=channel,
        ),
        session=session,
        x_bridge_secret=settings.bridge_secret,
    )
