import logging

from aiogram import Router, types
from aiogram.filters import Command
from sqlalchemy import select

from bot.keyboards.main import language_keyboard, main_menu_keyboard
from bot.locales import get_text
from db.database import async_session
from db.models import Language, User

router = Router()
logger = logging.getLogger(__name__)


@router.message(Command("lang"))
async def cmd_lang(message: types.Message):
    """Show language selection."""
    await message.answer("Tilni tanlang / Выберите язык:", reply_markup=language_keyboard())


@router.callback_query(lambda c: c.data and c.data.startswith("lang:"))
async def on_lang_select(callback: types.CallbackQuery):
    """Handle language selection."""
    lang_code = callback.data.split(":")[1]
    lang = Language(lang_code.upper())

    async with async_session() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == callback.from_user.id)
        )
        user = result.scalar_one_or_none()
        if not user:
            await callback.answer()
            return

        user.language = lang
        await session.commit()

    await callback.message.edit_text(
        get_text("language_changed", lang_code),
    )
    await callback.answer()

    # Show main menu in new language
    section_name = get_text(f"section_{user.active_section.value.lower()}", lang_code)
    await callback.message.answer(
        get_text("main_menu", lang_code, section=section_name),
        reply_markup=main_menu_keyboard(lang_code),
    )


@router.callback_query(lambda c: c.data == "action:settings")
async def on_settings(callback: types.CallbackQuery):
    """Handle settings button — show language selection for now."""
    await callback.message.edit_text(
        "Tilni tanlang / Выберите язык:",
        reply_markup=language_keyboard(),
    )
    await callback.answer()
