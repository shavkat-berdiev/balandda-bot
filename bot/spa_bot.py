"""@balandda_spa_bot — dedicated SPA notification bot.

Outbound messages are sent via services/spa_notify.py (raw HTTPS). This module
only runs a tiny polling handler so that:
- masters can press /start (required before any bot can DM them)
- the reply shows their Telegram ID to forward to Shavkat for registration
- an already-registered master gets a confirmation with their name

No-op while SPA_BOT_TOKEN is empty.
"""

import asyncio
import logging

from aiogram import Bot, Dispatcher, Router, types
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from sqlalchemy import select

from bot.config import settings
from db.database import async_session
from db.models import SpaMaster

logger = logging.getLogger(__name__)

spa_router = Router()


@spa_router.message()
async def any_message(message: types.Message):
    tid = message.from_user.id if message.from_user else None
    if not tid:
        return
    async with async_session() as session:
        master = (
            await session.execute(select(SpaMaster).where(SpaMaster.telegram_id == tid))
        ).scalar_one_or_none()
    if master:
        role = "внешний мастер" if master.master_type == "external" else "мастер"
        await message.answer(
            f"✅ Вы зарегистрированы как <b>{master.name}</b> ({role}).\n"
            f"Сюда будут приходить ваши записи и расписание на день."
        )
    elif settings.spa_admin_telegram_id and tid == settings.spa_admin_telegram_id:
        await message.answer(
            "✅ Вы подключены как <b>SPA администратор</b>.\n"
            "Сюда будут приходить все записи и расписание на день."
        )
    else:
        await message.answer(
            "👋 Это бот SPA Balandda.\n\n"
            f"Ваш Telegram ID: <code>{tid}</code>\n\n"
            "Отправьте этот номер Шавкату — после регистрации сюда будут "
            "приходить ваши записи."
        )


def start_spa_bot() -> tuple[Bot, asyncio.Task] | None:
    """Launch SPA bot polling as a background task. Returns None if disabled."""
    if not settings.spa_bot_token:
        logger.info("SPA bot disabled (SPA_BOT_TOKEN empty)")
        return None
    bot = Bot(
        token=settings.spa_bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher()
    dp.include_router(spa_router)
    task = asyncio.create_task(
        dp.start_polling(bot, allowed_updates=["message"], handle_signals=False)
    )
    logger.info("SPA bot polling started")
    return bot, task
