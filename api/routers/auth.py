"""Auth endpoints for Telegram Login Widget."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import select

from api.auth import create_session_token, verify_telegram_auth
from db.database import async_session
from db.models import User

router = APIRouter()


# --- Models (must be defined before endpoints) ---

class DevLoginData(BaseModel):
    telegram_id: int


class TelegramAuthData(BaseModel):
    id: int
    first_name: str
    last_name: str | None = None
    username: str | None = None
    photo_url: str | None = None
    auth_date: int
    hash: str


class TokenResponse(BaseModel):
    token: str
    user: dict


# --- Endpoints ---

@router.post("/dev-login", response_model=TokenResponse)
async def dev_login(data: DevLoginData):
    """Development-only login by Telegram ID (no verification)."""
    from bot.config import settings

    if settings.environment != "development":
        raise HTTPException(status_code=403, detail="Dev login only available in development mode")

    async with async_session() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == data.telegram_id)
        )
        user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    token = create_session_token(user.telegram_id, user.role.value)
    return TokenResponse(
        token=token,
        user={
            "telegram_id": user.telegram_id,
            "full_name": user.full_name,
            "role": user.role.value,
            "language": user.language.value,
        },
    )


@router.post("/telegram", response_model=TokenResponse)
async def telegram_login(auth_data: TelegramAuthData):
    """Authenticate via Telegram Login Widget."""
    data_dict = auth_data.model_dump(exclude_none=True)

    # Verify Telegram signature
    auth_dict = {k: str(v) for k, v in data_dict.items()}
    if not verify_telegram_auth(auth_dict):
        raise HTTPException(status_code=401, detail="Invalid Telegram auth data")

    # Check if user exists in our system
    async with async_session() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == auth_data.id)
        )
        user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=403,
            detail="You are not registered. Please use the Telegram bot first.",
        )

    if not user.is_active:
        raise HTTPException(status_code=403, detail="Your account is deactivated.")

    # Create session token
    token = create_session_token(user.telegram_id, user.role.value)

    return TokenResponse(
        token=token,
        user={
            "telegram_id": user.telegram_id,
            "full_name": user.full_name,
            "role": user.role.value,
            "language": user.language.value,
        },
    )
