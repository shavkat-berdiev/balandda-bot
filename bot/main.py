import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher, types
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


async def run_migrations():
    """Run schema migrations for columns added after initial table creation.

    SQLAlchemy's create_all() only creates new tables, it does NOT add
    columns to existing tables. We must ALTER TABLE manually.
    """
    migrations = [
        # Added in v0.2: restaurant income category on income_entries
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'income_entries'
                  AND column_name = 'restaurant_category'
            ) THEN
                ALTER TABLE income_entries
                ADD COLUMN restaurant_category VARCHAR(50) NULL;
            END IF;
        END $$;
        """,
    ]
    async with engine.begin() as conn:
        for sql in migrations:
            await conn.execute(text(sql))
    logger.info("Database migrations applied")


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


async def seed_new_tables():
    """Seed new structured report tables (properties, services, minibar, staff)."""
    from db.seed import seed_database

    async with async_session() as session:
        await seed_database(session)
    logger.info("New structured report tables seeded")


async def main():
    logger.info("Starting Balandda Bot...")

    # Initialize database
    await create_tables()
    await run_migrations()
    await seed_categories()
    await seed_new_tables()

    # Initialize bot
    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )

    dp = Dispatcher()
    dp.include_router(main_router)

    # Error handler
    @dp.error()
    async def error_handler(event: types.ErrorEvent):
        from aiogram.exceptions import TelegramBadRequest

        exc = event.exception

        # Suppress common non-critical Telegram API errors
        if isinstance(exc, TelegramBadRequest):
            msg = str(exc)
            if "message is not modified" in msg:
                logger.debug("Suppressed: message is not modified")
                return True
            if "message to edit not found" in msg:
                logger.debug("Suppressed: message to edit not found")
                return True
            if "query is too old" in msg:
                logger.debug("Suppressed: callback query too old")
                return True

        logger.error(
            f"Error handling update: {exc}",
            exc_info=exc,
        )

    # Setup scheduler for daily reports
    from bot.scheduler import setup_scheduler

    scheduler = setup_scheduler(bot)
    scheduler.start()
    logger.info("Scheduler started")

    # Start polling
    logger.info("Bot is running. Press Ctrl+C to stop.")
    try:
        await dp.start_polling(bot, allowed_updates=["message", "callback_query"])
    finally:
        scheduler.shutdown()
        await bot.session.close()
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
