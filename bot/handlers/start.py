import logging

from aiogram import Router, types
from aiogram.filters import Command, CommandStart
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards.main import main_menu_keyboard, section_keyboard
from bot.locales import get_text
from db.database import async_session
from db.models import BusinessUnit, Language, User, UserRole

router = Router()
logger = logging.getLogger(__name__)


async def get_or_create_user(telegram_id: int, full_name: str) -> User | None:
    """Get existing user or return None if not authorized."""
    async with async_session() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == telegram_id)
        )
        user = result.scalar_one_or_none()
        if user:
            # Update name if changed
            if user.full_name != full_name:
                user.full_name = full_name
                await session.commit()
        return user


async def create_admin_if_needed(telegram_id: int, full_name: str) -> User:
    """Create admin user (first-time setup)."""
    async with async_session() as session:
        user = User(
            telegram_id=telegram_id,
            full_name=full_name,
            role=UserRole.ADMIN,
            language=Language.RU,
            active_section=BusinessUnit.RESORT,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user


@router.message(CommandStart())
async def cmd_start(message: types.Message):
    """Handle /start command."""
    user = await get_or_create_user(message.from_user.id, message.from_user.full_name)

    if user is None:
        # Check if this is the admin (first user)
        from bot.config import settings

        if settings.admin_user_id and message.from_user.id == settings.admin_user_id:
            user = await create_admin_if_needed(
                message.from_user.id, message.from_user.full_name
            )
        else:
            # Check if any users exist (first user becomes admin)
            async with async_session() as session:
                result = await session.execute(select(User))
                if not result.scalars().first():
                    user = await create_admin_if_needed(
                        message.from_user.id, message.from_user.full_name
                    )
                else:
                    await message.answer(get_text("not_authorized"))
                    return

    lang = user.language.value.lower()
    await message.answer(
        get_text("welcome", lang),
        reply_markup=section_keyboard(lang),
    )


@router.callback_query(lambda c: c.data and c.data.startswith("section:"))
async def on_section_select(callback: types.CallbackQuery):
    """Handle section selection."""
    section = callback.data.split(":")[1]
    business_unit = BusinessUnit(section.upper())

    async with async_session() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == callback.from_user.id)
        )
        user = result.scalar_one_or_none()
        if not user:
            await callback.answer()
            return

        user.active_section = business_unit
        await session.commit()
        lang = user.language.value.lower()

    section_name = get_text(f"section_{section}", lang)
    await callback.message.edit_text(
        get_text("main_menu", lang, section=section_name),
        reply_markup=main_menu_keyboard(lang, current_section=section),
    )
    await callback.answer(get_text("switched_to", lang, section=section_name))


@router.message(Command("menu"))
async def cmd_menu(message: types.Message):
    """Show main menu for current section."""
    user = await get_or_create_user(message.from_user.id, message.from_user.full_name)
    if not user:
        await message.answer(get_text("not_authorized"))
        return

    lang = user.language.value.lower()
    section = user.active_section.value.lower()
    section_name = get_text(f"section_{section}", lang)
    await message.answer(
        get_text("main_menu", lang, section=section_name),
        reply_markup=main_menu_keyboard(lang, current_section=section),
    )
