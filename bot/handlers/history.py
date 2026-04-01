"""History handler — shows last N transactions for the current section."""

import logging
from datetime import datetime

from aiogram import F, Router, types
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import select

from bot.keyboards.main import main_menu_keyboard
from bot.locales import get_text
from db.database import async_session
from db.models import Category, Transaction, TransactionType, User

router = Router()
logger = logging.getLogger(__name__)

HISTORY_LIMIT = 10


@router.callback_query(F.data == "action:history")
async def on_history(callback: types.CallbackQuery):
    """Show last transactions for current section."""
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

        # Get recent transactions
        result = await session.execute(
            select(Transaction, Category)
            .join(Category, Transaction.category_id == Category.id)
            .where(Transaction.business_unit == user.active_section)
            .order_by(Transaction.created_at.desc())
            .limit(HISTORY_LIMIT)
        )
        rows = result.all()

    if not rows:
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

    # Build history text
    lines = [get_text("history_header", lang, count=len(rows)), ""]

    for tx, cat in rows:
        cat_name = cat.name_uz if lang == "uz" else cat.name_ru
        icon = "💰" if tx.transaction_type == TransactionType.CASH_IN else "💸"
        sign = "+" if tx.transaction_type == TransactionType.CASH_IN else "-"
        time_str = tx.created_at.strftime("%d.%m %H:%M")
        note_str = f" — {tx.note}" if tx.note else ""

        lines.append(f"{icon} {sign}{tx.amount:,.0f} UZS")
        lines.append(f"    {cat_name}{note_str}")
        lines.append(f"    🕐 {time_str}")
        lines.append("")

    back_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=f"◀️ {get_text('btn_back', lang)}",
            callback_data="action:back_menu",
        )]
    ])

    await callback.message.edit_text("\n".join(lines), reply_markup=back_kb)
    await callback.answer()
