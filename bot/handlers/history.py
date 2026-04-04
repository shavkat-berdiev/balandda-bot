"""History handler — shows last N entries from structured reports for the current section."""

import logging
from datetime import datetime

from aiogram import F, Router, types
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from bot.keyboards.main import main_menu_keyboard
from bot.locales import get_text
from db.database import async_session
from db.models import (
    ExpenseEntry,
    IncomeEntry,
    MinibarItem,
    Property,
    ServiceItem,
    StructuredReport,
    User,
)

router = Router()
logger = logging.getLogger(__name__)

HISTORY_LIMIT = 10


@router.callback_query(F.data == "action:history")
async def on_history(callback: types.CallbackQuery):
    """Show last entries from structured reports for current section."""
    async with async_session() as session:
        # Get user
        result = await session.execute(
            select(User).where(User.telegram_id == callback.from_user.id)
        )
        user = result.scalar_one_or_none()
        if not user:
            await callback.answer()
            return

        lang = user.language.value.lower()

        # Get recent structured reports for user's active section
        result = await session.execute(
            select(StructuredReport)
            .where(StructuredReport.business_unit == user.active_section)
            .options(
                selectinload(StructuredReport.income_entries).selectinload(IncomeEntry.property),
                selectinload(StructuredReport.income_entries).selectinload(IncomeEntry.service_item),
                selectinload(StructuredReport.income_entries).selectinload(IncomeEntry.minibar_item),
                selectinload(StructuredReport.expense_entries),
            )
            .order_by(StructuredReport.report_date.desc())
            .limit(5)
        )
        reports = result.scalars().all()

    if not reports:
        back_kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(
                text=f"◀️ {get_text('btn_back', lang)}",
                callback_data="action:back_menu",
            )]
        ])
        await callback.message.edit_text(
            get_text("history_empty", lang),
            reply_markup=back_kb,
        )
        await callback.answer()
        return

    # Build history text from structured reports
    lines = []
    entry_count = 0

    for report in reports:
        date_str = report.report_date.strftime("%d.%m.%Y")
        status_icon = "✅" if report.status.value == "SUBMITTED" else "📝"
        lines.append(f"📅 <b>{date_str}</b> {status_icon}")
        lines.append("")

        # Income entries
        for entry in report.income_entries:
            if entry_count >= HISTORY_LIMIT:
                break
            name = _get_income_name(entry, lang)
            amount_str = f"{entry.amount:,.0f}"
            payment = entry.payment_method.value if entry.payment_method else ""
            note_str = f" — {entry.note}" if entry.note else ""
            lines.append(f"  💰 +{amount_str} UZS")
            lines.append(f"      {name}{note_str}")
            if payment:
                lines.append(f"      💳 {payment}")
            lines.append("")
            entry_count += 1

        # Expense entries
        for entry in report.expense_entries:
            if entry_count >= HISTORY_LIMIT:
                break
            cat_name = entry.expense_category.value if entry.expense_category else "—"
            amount_str = f"{entry.amount:,.0f}"
            note_str = f" — {entry.note}" if entry.note else ""
            lines.append(f"  💸 -{amount_str} UZS")
            lines.append(f"      {entry.description or cat_name}{note_str}")
            lines.append("")
            entry_count += 1

        if entry_count >= HISTORY_LIMIT:
            break

    # Summary
    total_income = sum(
        sum(e.amount for e in r.income_entries) for r in reports
    )
    total_expense = sum(
        sum(e.amount for e in r.expense_entries) for r in reports
    )
    net = total_income - total_expense

    header = get_text("history_header", lang, count=entry_count)
    lines.insert(0, header)
    lines.insert(1, "")

    lines.append("──────────────")
    lines.append(f"💰 Доход: {total_income:,.0f} UZS")
    lines.append(f"💸 Расход: {total_expense:,.0f} UZS")
    lines.append(f"📊 Итого: {net:,.0f} UZS")

    back_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=f"◀️ {get_text('btn_back', lang)}",
            callback_data="action:back_menu",
        )]
    ])

    await callback.message.edit_text(
        "\n".join(lines),
        reply_markup=back_kb,
        parse_mode="HTML",
    )
    await callback.answer()


def _get_income_name(entry: IncomeEntry, lang: str) -> str:
    """Build a human-readable name for an income entry."""
    if entry.property:
        name = entry.property.name_ru if lang == "ru" else (getattr(entry.property, "name_uz", None) or entry.property.name_ru)
        return f"🏠 {name}"
    if entry.service_item:
        name = entry.service_item.name_ru if lang == "ru" else (getattr(entry.service_item, "name_uz", None) or entry.service_item.name_ru)
        return f"💆 {name}"
    if entry.minibar_item:
        name = entry.minibar_item.name_ru if lang == "ru" else (getattr(entry.minibar_item, "name_uz", None) or entry.minibar_item.name_ru)
        return f"🍹 {name}"
    if entry.restaurant_category:
        return f"🍽 {entry.restaurant_category.value}"
    return "📦 Прочее"
