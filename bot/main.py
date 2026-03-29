import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from sqlalchemy import text

from bot.config import settings
from bot.handlers import main_router
from db.database import async_session, engine
from db.models import Base

logging.basicConfig(
    level=getattr(logging, settings.log_level),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)


async def create_tables():
    """Create database tables if they don't exist."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables ready")


async def seed_categories():
    """Seed default categories if empty."""
    from db.models import BusinessUnit, Category, TransactionType

    async with async_session() as session:
        result = await session.execute(text("SELECT COUNT(*) FROM categories"))
        count = result.scalar()
        if count > 0:
            return

        categories = [
            # Resort — Income
            Category(name_ru="Оплата за проживание", name_uz="Yashash uchun to'lov",
                     business_unit=BusinessUnit.RESORT, transaction_type=TransactionType.CASH_IN, sort_order=1),
            Category(name_ru="СПА услуги", name_uz="SPA xizmatlari",
                     business_unit=BusinessUnit.RESORT, transaction_type=TransactionType.CASH_IN, sort_order=2),
            Category(name_ru="Минибар", name_uz="Minibar",
                     business_unit=BusinessUnit.RESORT, transaction_type=TransactionType.CASH_IN, sort_order=3),
            Category(name_ru="Доп. услуги", name_uz="Qo'shimcha xizmatlar",
                     business_unit=BusinessUnit.RESORT, transaction_type=TransactionType.CASH_IN, sort_order=4),
            # Resort — Expense
            Category(name_ru="Уборка и расходники", name_uz="Tozalash va sarf materiallari",
                     business_unit=BusinessUnit.RESORT, transaction_type=TransactionType.CASH_OUT, sort_order=1),
            Category(name_ru="Ремонт и обслуживание", name_uz="Ta'mirlash va xizmat ko'rsatish",
                     business_unit=BusinessUnit.RESORT, transaction_type=TransactionType.CASH_OUT, sort_order=2),
            Category(name_ru="Коммунальные услуги", name_uz="Kommunal xizmatlar",
                     business_unit=BusinessUnit.RESORT, transaction_type=TransactionType.CASH_OUT, sort_order=3),
            Category(name_ru="Зарплата", name_uz="Ish haqi",
                     business_unit=BusinessUnit.RESORT, transaction_type=TransactionType.CASH_OUT, sort_order=4),
            Category(name_ru="Бельё", name_uz="Choyshablar",
                     business_unit=BusinessUnit.RESORT, transaction_type=TransactionType.CASH_OUT, sort_order=5),
            # Restaurant — Income
            Category(name_ru="Продажа еды", name_uz="Ovqat sotish",
                     business_unit=BusinessUnit.RESTAURANT, transaction_type=TransactionType.CASH_IN, sort_order=1),
            Category(name_ru="Банкет / мероприятие", name_uz="Banket / tadbir",
                     business_unit=BusinessUnit.RESTAURANT, transaction_type=TransactionType.CASH_IN, sort_order=2),
            Category(name_ru="Доставка", name_uz="Yetkazib berish",
                     business_unit=BusinessUnit.RESTAURANT, transaction_type=TransactionType.CASH_IN, sort_order=3),
            Category(name_ru="Напитки", name_uz="Ichimliklar",
                     business_unit=BusinessUnit.RESTAURANT, transaction_type=TransactionType.CASH_IN, sort_order=4),
            # Restaurant — Expense
            Category(name_ru="Продукты", name_uz="Oziq-ovqat mahsulotlari",
                     business_unit=BusinessUnit.RESTAURANT, transaction_type=TransactionType.CASH_OUT, sort_order=1),
            Category(name_ru="Напитки (закуп)", name_uz="Ichimliklar (xarid)",
                     business_unit=BusinessUnit.RESTAURANT, transaction_type=TransactionType.CASH_OUT, sort_order=2),
            Category(name_ru="Зарплата", name_uz="Ish haqi",
                     business_unit=BusinessUnit.RESTAURANT, transaction_type=TransactionType.CASH_OUT, sort_order=3),
            Category(name_ru="Оборудование", name_uz="Jihozlar",
                     business_unit=BusinessUnit.RESTAURANT, transaction_type=TransactionType.CASH_OUT, sort_order=4),
            Category(name_ru="Коммунальные услуги", name_uz="Kommunal xizmatlar",
                     business_unit=BusinessUnit.RESTAURANT, transaction_type=TransactionType.CASH_OUT, sort_order=5),
        ]

        session.add_all(categories)
        await session.commit()
        logger.info(f"Seeded {len(categories)} default categories")


async def main():
    logger.info("Starting Balandda Bot...")

    # Initialize database
    await create_tables()
    await seed_categories()

    # Initialize bot
    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )

    dp = Dispatcher()
    dp.include_router(main_router)

    # Start polling
    logger.info("Bot is running. Press Ctrl+C to stop.")
    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        await bot.session.close()
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
