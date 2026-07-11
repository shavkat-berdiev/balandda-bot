"""Daily auto-report sender — sends summary at 21:00 Tashkent time."""

import logging
from datetime import date, datetime, timezone

from aiogram import Bot
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from bot.config import settings
from db.database import async_session
from services import beds24
from db.enums import (
    EXPENSE_CATEGORY_LABELS,
    PAYMENT_METHOD_LABELS,
    ReportStatus,
    ReservationStatus,
)
from db.models import (
    ExpenseEntry,
    IncomeEntry,
    MinibarItem,
    Property,
    Reservation,
    ReservationEvent,
    ServiceItem,
    StructuredReport,
    User,
    UserRole,
)

logger = logging.getLogger(__name__)


def format_amount(amount: float) -> str:
    """Format amount with dot separators (e.g., 3.200.000)."""
    return f"{amount:,.0f}".replace(",", ".")


async def build_daily_summary(target_date: date) -> str:
    """Build a daily summary from all structured reports for the date."""
    async with async_session() as session:
        result = await session.execute(
            select(StructuredReport)
            .where(
                StructuredReport.report_date == target_date,
                StructuredReport.status != ReportStatus.DRAFT,
            )
            .options(
                selectinload(StructuredReport.income_entries).selectinload(IncomeEntry.property),
                selectinload(StructuredReport.income_entries).selectinload(IncomeEntry.service_item),
                selectinload(StructuredReport.income_entries).selectinload(IncomeEntry.minibar_item),
                selectinload(StructuredReport.expense_entries),
            )
        )
        reports = result.scalars().all()

    if not reports:
        return f"📊 Отчёт за {target_date.strftime('%d.%m.%Y')}\n\nНет отправленных отчётов за сегодня."

    total_income = sum(float(r.total_income or 0) for r in reports)
    total_expense = sum(float(r.total_expense or 0) for r in reports)
    net = total_income - total_expense

    lines = [
        f"📊 Ежедневный отчёт — {target_date.strftime('%d.%m.%Y')}",
        "",
        f"💰 Доход: {format_amount(total_income)} UZS",
        f"💸 Расход: {format_amount(total_expense)} UZS",
        f"{'📈' if net >= 0 else '📉'} Чистый доход: {format_amount(net)} UZS",
        "",
    ]

    # Group income by property
    property_totals: dict[str, float] = {}
    service_totals: dict[str, float] = {}
    minibar_total = 0.0

    for report in reports:
        for entry in report.income_entries:
            if entry.property:
                name = entry.property.name_ru
                property_totals[name] = property_totals.get(name, 0) + float(entry.amount)
            elif entry.service_item:
                name = entry.service_item.name_ru
                service_totals[name] = service_totals.get(name, 0) + float(entry.amount)
            elif entry.minibar_item:
                minibar_total += float(entry.amount)

    if property_totals:
        lines.append("🏠 Проживание:")
        for name, total in sorted(property_totals.items()):
            lines.append(f"  • {name}: {format_amount(total)}")

    if service_totals:
        lines.append("\n💆 Услуги:")
        for name, total in sorted(service_totals.items()):
            lines.append(f"  • {name}: {format_amount(total)}")

    if minibar_total > 0:
        lines.append(f"\n🍹 Мини-бар: {format_amount(minibar_total)}")

    # Expense breakdown
    expense_totals: dict[str, float] = {}
    for report in reports:
        for entry in report.expense_entries:
            label = EXPENSE_CATEGORY_LABELS.get(entry.expense_category, entry.expense_category.value)
            expense_totals[label] = expense_totals.get(label, 0) + float(entry.amount)

    if expense_totals:
        lines.append("\n💸 Расходы:")
        for label, total in sorted(expense_totals.items(), key=lambda x: x[1], reverse=True):
            lines.append(f"  • {label}: {format_amount(total)}")

    lines.append(f"\n📝 Отчётов: {len(reports)}")

    return "\n".join(lines)


async def send_daily_report(bot: Bot):
    """Send daily report to all admins."""
    today = date.today()
    logger.info(f"Sending daily report for {today}")

    try:
        summary = await build_daily_summary(today)

        # Find admins to notify
        async with async_session() as session:
            result = await session.execute(
                select(User).where(
                    User.role == UserRole.ADMIN,
                    User.is_active == True,
                )
            )
            admins = result.scalars().all()

        if not admins:
            logger.warning("No active admins found to send daily report")
            return

        for admin in admins:
            try:
                await bot.send_message(admin.telegram_id, summary)
                logger.info(f"Daily report sent to admin {admin.full_name} ({admin.telegram_id})")
            except Exception as e:
                logger.error(f"Failed to send daily report to {admin.telegram_id}: {e}")

    except Exception as e:
        logger.error(f"Error building daily report: {e}", exc_info=True)


async def send_balance_reminders(bot: Bot):
    """At 21:00 remind each admin/owner who is holding cash about their balance."""
    from bot.handlers.wallet import get_wallet_balance

    async with async_session() as session:
        result = await session.execute(
            select(User).where(
                User.role.in_([UserRole.ADMIN, UserRole.OWNER]),
                User.is_active == True,
            )
        )
        users = result.scalars().all()

    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="💰 Открыть кошелёк", callback_data="action:wallet"),
    ]])
    for u in users:
        try:
            bal = await get_wallet_balance(u.telegram_id)
            if float(bal) == 0:
                continue  # nothing on hand — don't ping
            await bot.send_message(
                u.telegram_id,
                f"💰 <b>Остаток наличных на конец дня</b>\n\n"
                f"Ваш баланс: <b>{format_amount(float(bal))} UZS</b>\n\n"
                f"Не забудьте сдать инкассацию.",
                reply_markup=kb,
            )
        except Exception as e:
            logger.error(f"Balance reminder failed for {u.telegram_id}: {e}")


async def _safe_send(bot: Bot, chat_id: int, text: str) -> None:
    try:
        await bot.send_message(chat_id, text)
    except Exception as e:
        logger.warning(f"Hold notification to {chat_id} failed: {e}")


async def process_hold_expiries(bot: Bot):
    """Warn and expire unpaid booking holds.

    Timers (warn +30m, expire +60m of working time) were computed at booking creation,
    so we only compare against them here. Runs every few minutes. First payment already
    cleared the timers, so only still-unpaid HOLDs are ever touched.
    """
    now = datetime.now(timezone.utc)
    expired_any = False
    async with async_session() as session:
        holds = (
            await session.execute(
                select(Reservation).where(
                    Reservation.status == ReservationStatus.HOLD,
                    Reservation.hold_expires_at.is_not(None),
                )
            )
        ).scalars().all()

        for res in holds:
            prop = await session.get(Property, res.property_id)
            unit = prop.name_ru if prop else str(res.property_id)
            who = res.guest_name or (f"@{res.telegram_username}" if res.telegram_username else "гость")
            dates = f"{res.check_in.strftime('%d.%m')}–{res.check_out.strftime('%d.%m')}"
            label = f"{unit} · {who} · {dates}"

            # Expire (checked first, in case the scheduler was paused past both points)
            if res.hold_expires_at and now >= res.hold_expires_at:
                res.status = ReservationStatus.EXPIRED
                expired_any = True
                session.add(ReservationEvent(
                    reservation_id=res.id, actor_name="Авто (таймер)", action="auto",
                    detail="Бронь истекла: предоплата не внесена вовремя. Дата освобождена.",
                ))
                await session.commit()
                if res.created_by:
                    await _safe_send(bot, res.created_by, f"⌛️ Бронь истекла (не оплачена): {label}. Дата освобождена.")
                if res.telegram_user_id:
                    await _safe_send(bot, res.telegram_user_id,
                                     f"К сожалению, ваша бронь ({unit}, {dates}) отменена — предоплата не поступила вовремя.")
                continue

            # Warn once
            if res.hold_warn_at and now >= res.hold_warn_at and res.hold_warned_at is None:
                res.hold_warned_at = now
                await session.commit()
                if res.created_by:
                    tg = f" (@{res.telegram_username})" if res.telegram_username else ""
                    await _safe_send(bot, res.created_by,
                                     f"⚠️ Бронь без предоплаты: {label}{tg}. Свяжитесь с клиентом — через 30 минут авто-отмена.")
                if res.telegram_user_id:
                    await _safe_send(bot, res.telegram_user_id,
                                     f"⚠️ Ваша бронь ({unit}, {dates}) ещё не оплачена. Пожалуйста, внесите предоплату в течение 30 минут, иначе бронь будет отменена.")

    if expired_any:
        beds24.kick()  # expired holds freed dates → update the OTA channels


def setup_scheduler(bot: Bot) -> AsyncIOScheduler:
    """Set up and return the APScheduler instance."""
    scheduler = AsyncIOScheduler(timezone=settings.timezone)

    scheduler.add_job(
        process_hold_expiries,
        IntervalTrigger(minutes=5),
        args=[bot],
        id="hold_expiries",
        name="Booking hold expiries",
        replace_existing=True,
    )

    scheduler.add_job(
        send_daily_report,
        CronTrigger(
            hour=settings.daily_report_hour,
            minute=settings.daily_report_minute,
            timezone=settings.timezone,
        ),
        args=[bot],
        id="daily_report",
        name="Daily Report",
        replace_existing=True,
    )

    scheduler.add_job(
        send_balance_reminders,
        CronTrigger(
            hour=settings.daily_report_hour,
            minute=settings.daily_report_minute,
            timezone=settings.timezone,
        ),
        args=[bot],
        id="balance_reminders",
        name="Balance Reminders",
        replace_existing=True,
    )

    # Beds24 channel-manager sync (no-ops unless BEDS24_ENABLED)
    scheduler.add_job(
        beds24.pull_bookings,
        IntervalTrigger(minutes=5),
        id="beds24_pull",
        name="Beds24: import OTA bookings",
        replace_existing=True,
    )
    scheduler.add_job(
        beds24.push_full,
        IntervalTrigger(minutes=60),
        id="beds24_push",
        name="Beds24: full availability/price push",
        replace_existing=True,
    )

    logger.info(
        f"Scheduler configured: daily report at "
        f"{settings.daily_report_hour:02d}:{settings.daily_report_minute:02d} "
        f"{settings.timezone}"
    )

    return scheduler
