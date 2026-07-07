"""Bridge endpoints called by the CRM (@balandda_bot) — secret-authed.

When a customer taps the connect deep-link, the CRM bot reports their Telegram id
here; we attach it to the booking and return the booking-received text for the CRM
to reply with.
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import settings
from db.database import get_session
from db.models import Property, Reservation
from services.customer_notify import booking_received_text

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

    return {
        "ok": True,
        "already": already,
        "message": booking_received_text(res, prop.name_ru if prop else ""),
    }
