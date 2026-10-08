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
