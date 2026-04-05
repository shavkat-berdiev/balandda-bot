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
        # Added in v0.3: OPERATOR role
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_enum
                WHERE enumlabel = 'OPERATOR'
                  AND enumtypid = (SELECT oid FROM pg_type WHERE typname = 'userrole')
            ) THEN
                ALTER TYPE userrole ADD VALUE 'OPERATOR';
            END IF;
        END $$;
        """,
        # Added in v0.3: PrepaymentStatus enum type
        """
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'prepaymentstatus') THEN
                CREATE TYPE prepaymentstatus AS ENUM ('PENDING', 'CONFIRMED', 'SETTLED', 'CANCELLED');
            END IF;
        END $$;
        """,
        # Added in v0.3: prepayments table
        """
        CREATE TABLE IF NOT EXISTS prepayments (
            id SERIAL PRIMARY KEY,
            guest_name VARCHAR(255) NOT NULL,
            property_id INTEGER NOT NULL REFERENCES properties(id),
            check_in_date DATE NOT NULL,
            check_out_date DATE NOT NULL,
            amount NUMERIC(15,2) NOT NULL,
            payment_method VARCHAR(50) NOT NULL DEFAULT 'CARD_TRANSFER',
            status prepaymentstatus NOT NULL DEFAULT 'PENDING',
            screenshot_file_id VARCHAR(255),
            note TEXT,
            operator_telegram_id BIGINT NOT NULL,
            settled_in_report_id INTEGER REFERENCES structured_reports(id),
            created_at TIMESTAMPTZ DEFAULT NOW(),
            updated_at TIMESTAMPTZ DEFAULT NOW()
        );
        """,
        # Index on check_in_date for calendar queries
        """
        CREATE INDEX IF NOT EXISTS ix_prepayments_check_in_date ON prepayments (check_in_date);
        """,
        # Index on operator
        """
        CREATE INDEX IF NOT EXISTS ix_prepayments_operator ON prepayments (operator_telegram_id);
        """,
        # Added in v0.4: WalletTransactionType enum
        """
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'wallettransactiontype') THEN
                CREATE TYPE wallettransactiontype AS ENUM ('CASH_IN', 'TRANSFER_TO_EMPLOYEE', 'TRANSFER_TO_SHAVKAT', 'CASH_TO_BANK');
            END IF;
        END $$;
        """,
        # Added in v0.4: wallet_transactions table
        """
        CREATE TABLE IF NOT EXISTS wallet_transactions (
            id SERIAL PRIMARY KEY,
            sender_telegram_id BIGINT NOT NULL,
            receiver_telegram_id BIGINT,
            amount NUMERIC(15,2) NOT NULL,
            transaction_type wallettransactiontype NOT NULL,
            note TEXT,
            report_id INTEGER REFERENCES structured_reports(id),
            business_unit VARCHAR(20),
            created_at TIMESTAMPTZ DEFAULT NOW()
        );
        """,
        """
        CREATE INDEX IF NOT EXISTS ix_wallet_tx_sender ON wallet_transactions (sender_telegram_id);
        """,
        """
        CREATE INDEX IF NOT EXISTS ix_wallet_tx_receiver ON wallet_transactions (receiver_telegram_id);
        """,
        # Added in v0.4: PREPAYMENT value for paymentmethod enum (if missing)
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_enum
                WHERE enumlabel = 'PREPAYMENT'
                  AND enumtypid = (SELECT oid FROM pg_type WHERE typname = 'paymentmethod')
            ) THEN
                ALTER TYPE paymentmethod ADD VALUE 'PREPAYMENT';
            END IF;
        END $$;
        """,
        # Added in v0.5: RegistrationRequestStatus enum
        """
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'registrationrequeststatus') THEN
                CREATE TYPE registrationrequeststatus AS ENUM ('PENDING', 'APPROVED', 'REJECTED');
            END IF;
        END $$;
        """,
        # Added in v0.5: registration_requests table
        """
        CREATE TABLE IF NOT EXISTS registration_requests (
            id SERIAL PRIMARY KEY,
            telegram_id BIGINT NOT NULL,
            full_name VARCHAR(255) NOT NULL,
            username VARCHAR(255),
            status registrationrequeststatus NOT NULL DEFAULT 'PENDING',
            reviewed_by BIGINT,
            assigned_role userrole,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            reviewed_at TIMESTAMPTZ
        );
        """,
        """
        CREATE INDEX IF NOT EXISTS ix_registration_requests_tid ON registration_requests (telegram_id);
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
