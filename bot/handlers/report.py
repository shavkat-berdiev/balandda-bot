"""Report handler — daily summary for current section."""

import logging
from datetime import date, datetime, timedelta

from aiogram import F, Router, types
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import func, select

from bot.keyboards.main import main_menu_keyboard
from bot.locales import get_text
from db.database import async_session
from db.models import Category, Transaction, TransactionType, User

router = Router()
logger = logging.getLogger(__name__)


async def build_daily_report(business_unit, target_date: date, lang: str) -> str:
    """Build daily report text."""
    start = datetime.combine(target_date, datetime.min.time())
    end = datetime.combine(target_date, datetime.max.time())

    async with async_session() as session:
        # Totals
        result = await session.execute(
            select(
                Transaction.transaction_type,
                func.coalesce(func.sum(Transaction.amount), 0).label("total"),
            )
            .where(
                Transaction.business_unit == business_unit,
                Transaction.created_at >= start,
                Transaction.created_at <= end,
            )
            .group_by(Transaction.transaction_type)
        )
        totals = {row.transaction_type: float(row.total) for row in result}

        total_in = totals.get(TransactionType.CASH_IN, 0)
        total_out = totals.get(TransactionType.CASH_OUT, 0)
        net = total_in - total_out

        # By category
        result = await session.execute(
            select(
                Category.name_ru,
                Category.name_uz,
                Transaction.transaction_type,
                func.sum(Transaction.amount).label("total"),
            )
            .join(Category, Transaction.category_id == Category.id)
            .where(
                Transaction.business_unit == business_unit,
                Transaction.created_at >= start,
                Transaction.created_at <= end,
            )
            .group_by(Category.name_ru, Category.name_uz, Transaction.transaction_type)
        )
        categories = result.all()

    date_str = target_date.strftime("%d.%m.%Y")
    section_name = get_text(f"section_{business_unit.value}", lang)
    lines = [
        f"📊 {get_text('report_today', lang, section=section_name)}",
        f"📅 {date_str}",
        "",
        get_text("report_total_in", lang, amount=total_in),
        get_text("report_total_out", lang, amount=total_out),
        f"{'📈' if net >= 0 else '📉'} {get_text('report_net', lang, amount=net)}",
    ]

    # Category breakdown
    cash_in_cats = [c for c in categories if c.transaction_type == TransactionType.CASH_IN]
    cash_out_cats = [c for c in categories if c.transaction_type == TransactionType.CASH_OUT]

    if cash_in_cats:
        lines.append("")
        lines.append(f"💰 {get_text('btn_cash_in', lang)}:")
        for cat in cash_in_cats:
            name = cat.name_uz if lang == "uz" else cat.name_ru
            lines.append(f"  • {name}: {float(cat.total):,.0f} UZS")

    if cash_out_cats:
        lines.append("")
        lines.append(f"💸 {get_text('btn_cash_out', lang)}:")
        for cat in cash_out_cats:
            name = cat.name_uz if lang == "uz" else cat.name_ru
            lines.append(f"  • {name}: {float(cat.total):,.0f} UZS")

    if not cash_in_cats and not cash_out_cats:
        lines.append("")
        lines.append(get_text("history_empty", lang))

    return "\n".join(lines)


@router.callback_query(F.data == "action:report")
async def on_report(callback: types.CallbackQuery):
    """Show today's report for current section."""
    async with async_session() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == callback.from_user.id)
        )
        user = result.scalar_one_or_none()

    if not user:
        await callback.answer()
        return

    lang = user.language.value.lower()
    report_text = await build_daily_report(user.active_section, date.today(), lang)

    back_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=f"◀️ {get_text('btn_back', lang)}",
            callback_data="action:back_menu",
        )]
    ])

    await callback.message.edit_text(report_text, reply_markup=back_kb)
    await callback.answer()


# --- Back to menu handler ---

@router.callback_query(F.data == "action:back_menu")
async def on_back_menu(callback: types.CallbackQuery):
    """Return to main menu."""
    async with async_session() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == callback.from_user.id)
        )
        user = result.scalar_one_or_none()

    if not user:
        await callback.answer()
        return

    lang = user.language.value.lower()
    section = user.active_section.value.lower()
    section_name = get_text(f"section_{section}", lang)

    await callback.message.edit_text(
        get_text("main_menu", lang, section=section_name),
        reply_markup=main_menu_keyboard(lang, current_section=section),
    )
    await callback.answer()
