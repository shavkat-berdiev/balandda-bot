"""Daily auto-report sender — sends summary at 21:00 Tashkent time."""

import logging
from datetime import date, datetime

from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from bot.config import settings
from db.database import async_session
from db.enums import (
    EXPENSE_CATEGORY_LABELS,
    PAYMENT_METHOD_LABELS,
    ReportStatus,
)
from db.models import (
    ExpenseEntry,
    IncomeEntry,
    MinibarItem,
    Property,
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


def setup_scheduler(bot: Bot) -> AsyncIOScheduler:
    """Set up and return the APScheduler instance."""
    scheduler = AsyncIOScheduler(timezone=settings.timezone)

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

    logger.info(
        f"Scheduler configured: daily report at "
        f"{settings.daily_report_hour:02d}:{settings.daily_report_minute:02d} "
        f"{settings.timezone}"
    )

    return scheduler
