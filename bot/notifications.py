"""Shared notification module — sends activity logs to OWNER users via Telegram."""

import logging

from aiogram import Bot
from sqlalchemy import select

from db.database import async_session
from db.enums import UserRole
from db.models import User

logger = logging.getLogger(__name__)


async def _get_owner_ids() -> list[int]:
    """Fetch telegram_ids of all active OWNER users."""
    async with async_session() as session:
        result = await session.execute(
            select(User.telegram_id).where(
                User.role == UserRole.OWNER,
                User.is_active == True,
            )
        )
        return [row[0] for row in result.all()]


async def notify_owners(bot: Bot, text: str):
    """Send a notification message to all OWNER users."""
    owner_ids = await _get_owner_ids()
    for tid in owner_ids:
        try:
            await bot.send_message(tid, text, parse_mode="HTML")
        except Exception as e:
            logger.error(f"Failed to notify owner {tid}: {e}")


def format_amount(amount) -> str:
    """Format number as readable currency string."""
    return f"{int(float(amount)):,}".replace(",", " ")


async def notify_report_submitted(bot: Bot, user_name: str, report_date, business_unit: str,
                                   total_income: float, total_expense: float,
                                   income_count: int, expense_count: int):
    """Notify owners when a report is submitted."""
    bu_label = "Курорт" if business_unit == "RESORT" else "Ресторан"
    net = total_income - total_expense
    text = (
        f"📋 <b>Отчёт отправлен</b>\n\n"
        f"👤 {user_name}\n"
        f"📅 {report_date}\n"
        f"🏢 {bu_label}\n"
        f"📈 Доход: {format_amount(total_income)} UZS ({income_count} шт.)\n"
        f"📉 Расход: {format_amount(total_expense)} UZS ({expense_count} шт.)\n"
        f"💰 Итого: {'+' if net >= 0 else ''}{format_amount(net)} UZS"
    )
    await notify_owners(bot, text)


async def notify_prepayment_created(bot: Bot, operator_name: str, guest_name: str,
                                     property_name: str, check_in: str, check_out: str,
                                     amount: float, payment_method: str):
    """Notify owners when a prepayment is created."""
    text = (
        f"💵 <b>Новая предоплата</b>\n\n"
        f"👤 Оператор: {operator_name}\n"
        f"🧑 Гость: {guest_name}\n"
        f"🏠 {property_name}\n"
        f"📅 {check_in} → {check_out}\n"
        f"💰 {format_amount(amount)} UZS\n"
        f"💳 {payment_method}"
    )
    await notify_owners(bot, text)


async def notify_wallet_transfer(bot: Bot, sender_name: str, tx_label: str,
                                  receiver_name: str, amount: float, note: str | None = None):
    """Notify owners when a wallet transfer is made."""
    note_text = f"\n📝 {note}" if note else ""
    text = (
        f"💼 <b>Операция кошелька</b>\n\n"
        f"👤 {sender_name}\n"
        f"🔄 {tx_label}\n"
        f"➡️ {receiver_name}\n"
        f"💰 {format_amount(amount)} UZS{note_text}"
    )
    await notify_owners(bot, text)


async def notify_income_entry(bot: Bot, user_name: str, entry_name: str,
                               amount: float, payment_label: str, business_unit: str):
    """Notify owners when an income entry is added to a report."""
    bu_label = "Курорт" if business_unit == "RESORT" else "Ресторан"
    text = (
        f"📈 <b>Новый доход</b>\n\n"
        f"👤 {user_name}\n"
        f"🏢 {bu_label}\n"
        f"📝 {entry_name}\n"
        f"💰 {format_amount(amount)} UZS\n"
        f"💳 {payment_label}"
    )
    await notify_owners(bot, text)


async def notify_expense_entry(bot: Bot, user_name: str, category_label: str,
                                amount: float, description: str, business_unit: str):
    """Notify owners when an expense entry is added to a report."""
    bu_label = "Курорт" if business_unit == "RESORT" else "Ресторан"
    text = (
        f"📉 <b>Новый расход</b>\n\n"
        f"👤 {user_name}\n"
        f"🏢 {bu_label}\n"
        f"📝 {category_label}: {description}\n"
        f"💰 {format_amount(amount)} UZS"
    )
    await notify_owners(bot, text)
