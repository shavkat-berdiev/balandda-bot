"""Bridge endpoints called by the CRM (@balandda_bot) — secret-authed.

When a customer taps the connect deep-link, the CRM bot reports their Telegram id
here; we attach it to the booking and return the booking-received text for the CRM
to reply with.
"""

from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from api.routers.public import _stay_total
from bot.config import settings
from db.database import get_session
from db.enums import ReservationSource, ReservationStatus
from db.hold_timing import add_working_minutes
from db.models import Property, Reservation, ReservationEvent
from services.customer_notify import booking_received_text, get_prepayment_instructions

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
    telegram_user_id: int
    telegram_username: str | None = None


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

    now = datetime.now(timezone.utc)
    total = _stay_total(prop.price_weekday, prop.price_weekend, data.check_in, data.check_out)
    res = Reservation(
        property_id=prop.id,
        check_in=data.check_in,
        check_out=data.check_out,
        guest_name=data.guest_name,
        guest_phone=data.guest_phone,
        guest_count=data.guests,
        telegram_user_id=data.telegram_user_id,
        telegram_username=(data.telegram_username.lstrip("@") if data.telegram_username else None),
        status=ReservationStatus.HOLD,
        source=ReservationSource.TELEGRAM,
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

    prepay_text = await get_prepayment_instructions()
    return {"ok": True, "booking_id": res.id, "message": booking_received_text(res, prop.name_ru, prepay_text)}
