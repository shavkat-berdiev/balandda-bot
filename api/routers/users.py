"""User management endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth import get_current_user
from db.database import get_session
from db.models import BusinessUnit, Language, User, UserRole

router = APIRouter()


class UserOut(BaseModel):
    id: int
    telegram_id: int
    full_name: str
    role: str
    language: str
    active_section: str
    is_active: bool
    created_at: str

    model_config = {"from_attributes": True}


class UserCreate(BaseModel):
    telegram_id: int
    full_name: str
    role: UserRole = UserRole.RESORT_MANAGER


class UserUpdate(BaseModel):
    role: UserRole | None = None
    is_active: bool | None = None
    active_section: BusinessUnit | None = None


@router.get("/", response_model=list[UserOut])
async def list_users(
    session: AsyncSession = Depends(get_session),
    user: dict = Depends(get_current_user),
):
    """List all users (admin only)."""
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")

    result = await session.execute(select(User).order_by(User.created_at))
    users = result.scalars().all()
    return [
        UserOut(
            id=u.id,
            telegram_id=u.telegram_id,
            full_name=u.full_name,
            role=u.role.value,
            language=u.language.value,
            active_section=u.active_section.value,
            is_active=u.is_active,
            created_at=u.created_at.isoformat() if u.created_at else "",
        )
        for u in users
    ]


@router.post("/", response_model=UserOut)
async def create_user(
    data: UserCreate,
    session: AsyncSession = Depends(get_session),
    user: dict = Depends(get_current_user),
):
    """Add a new manager user (admin only)."""
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")

    # Check if telegram_id already exists
    result = await session.execute(
        select(User).where(User.telegram_id == data.telegram_id)
    )
    if result.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="User with this Telegram ID already exists")

    new_user = User(
        telegram_id=data.telegram_id,
        full_name=data.full_name,
        role=data.role,
        language=Language.RU,
        active_section=BusinessUnit.RESORT,
    )
    session.add(new_user)
    await session.commit()
    await session.refresh(new_user)

    return UserOut(
        id=new_user.id,
        telegram_id=new_user.telegram_id,
        full_name=new_user.full_name,
        role=new_user.role.value,
        language=new_user.language.value,
        active_section=new_user.active_section.value,
        is_active=new_user.is_active,
        created_at=new_user.created_at.isoformat() if new_user.created_at else "",
    )


@router.put("/{user_id}", response_model=UserOut)
async def update_user(
    user_id: int,
    data: UserUpdate,
    session: AsyncSession = Depends(get_session),
    user: dict = Depends(get_current_user),
):
    """Update a user's role or status (admin only)."""
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")

    result = await session.execute(select(User).where(User.id == user_id))
    target = result.scalar_one_or_none()
    if not target:
        raise HTTPException(status_code=404, detail="User not found")

    for field, value in data.model_dump(exclude_none=True).items():
        setattr(target, field, value)

    await session.commit()
    await session.refresh(target)

    return UserOut(
        id=target.id,
        telegram_id=target.telegram_id,
        full_name=target.full_name,
        role=target.role.value,
        language=target.language.value,
        active_section=target.active_section.value,
        is_active=target.is_active,
        created_at=target.created_at.isoformat() if target.created_at else "",
    )
