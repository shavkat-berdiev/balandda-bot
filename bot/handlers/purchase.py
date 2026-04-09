"""Purchase handler — employees submit grouped purchase reports.

Flow:
1. User taps "🛒 Закуп" → create/get draft purchase report for today
2. Show purchase action menu: add entry, preview, finalize
3. Add entry: pick category → enter amount → enter description → confirm
4. On finalize: mark as SUBMITTED, deduct total from wallet, notify owners
"""

import logging
from datetime import date
from decimal import Decimal

from aiogram import F, Router, types
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import select

from bot.keyboards.main import main_menu_keyboard
from bot.locales import get_text
from bot.notifications import notify_owners
from db.database import async_session
from db.enums import (
    BusinessUnit,
    PurchaseCategory,
    PURCHASE_CATEGORY_LABELS,
    PURCHASE_CATEGORIES_RESORT,
    PURCHASE_CATEGORIES_RESTAURANT,
    WalletTransactionType,
    WalletTransactionStatus,
)
from db.models import (
    PurchaseEntry,
    PurchaseReport,
    ReportStatus,
    User,
    WalletTransaction,
)

router = Router()
logger = logging.getLogger(__name__)


class PurchaseStates(StatesGroup):
    choosing_action = State()
    choosing_category = State()
    entering_amount = State()
    entering_description = State()
    confirming_entry = State()


def format_amount(amount) -> str:
    if isinstance(amount, Decimal):
        amount = float(amount)
    return f"{amount:,.0f}".replace(",", ".")


async def get_user(telegram_id: int) -> User | None:
    async with async_session() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == telegram_id)
        )
        return result.scalar_one_or_none()


async def get_or_create_draft_purchase(user_tid: int, report_date: date, bu: BusinessUnit) -> PurchaseReport:
    """Get or create a draft purchase report for today."""
    async with async_session() as session:
        result = await session.execute(
            select(PurchaseReport).where(
                PurchaseReport.user_telegram_id == user_tid,
                PurchaseReport.report_date == report_date,
                PurchaseReport.business_unit == bu,
                PurchaseReport.status == ReportStatus.DRAFT,
            )
        )
        report = result.scalar_one_or_none()
        if report:
            return report

        report = PurchaseReport(
            user_telegram_id=user_tid,
            report_date=report_date,
            business_unit=bu,
            status=ReportStatus.DRAFT,
            total_amount=Decimal(0),
        )
        session.add(report)
        await session.commit()
        await session.refresh(report)
        return report


def build_purchase_action_menu(lang: str, entry_count: int = 0, total: float = 0) -> InlineKeyboardMarkup:
    """Build the main purchase action menu."""
    buttons = [
        [InlineKeyboardButton(text="🛒 Добавить позицию", callback_data="pur:add")],
    ]
    if entry_count > 0:
        buttons.append([InlineKeyboardButton(
            text=f"👁 Просмотр ({entry_count} шт, {format_amount(total)} UZS)",
            callback_data="pur:preview",
        )])
        buttons.append([InlineKeyboardButton(
            text="✅ Завершить закуп",
            callback_data="pur:finalize",
        )])
    buttons.append([InlineKeyboardButton(text="❌ Отмена", callback_data="pur:cancel")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def build_category_keyboard(business_unit: str) -> InlineKeyboardMarkup:
    """Build category selection keyboard based on business unit."""
    if business_unit == "RESTAURANT":
        categories = PURCHASE_CATEGORIES_RESTAURANT
    else:
        categories = PURCHASE_CATEGORIES_RESORT

    buttons = []
    for cat in categories:
        label = PURCHASE_CATEGORY_LABELS.get(cat, cat.value)
        buttons.append([InlineKeyboardButton(
            text=label,
            callback_data=f"purcat:{cat.value}",
        )])
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="pur:back")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


# ────────────────────────────────────────────────────────────────────────
# ENTRY POINT
# ────────────────────────────────────────────────────────────────────────


@router.callback_query(F.data == "action:purchase")
async def on_purchase_start(callback: types.CallbackQuery, state: FSMContext):
    """Start purchase flow — create/get draft report."""
    user = await get_user(callback.from_user.id)
    if not user:
        await callback.answer("Пользователь не найден")
        return

    lang = user.language.value.lower()
    bu = user.active_section
    bu_label = "Курорт" if bu == BusinessUnit.RESORT else "Ресторан"

    report = await get_or_create_draft_purchase(
        user.telegram_id, date.today(), bu,
    )

    # Count existing entries
    async with async_session() as session:
        from sqlalchemy.orm import selectinload
        result = await session.execute(
            select(PurchaseReport)
            .where(PurchaseReport.id == report.id)
            .options(selectinload(PurchaseReport.entries))
        )
        report = result.scalar_one()

    entry_count = len(report.entries)
    total = float(report.total_amount or 0)

    await state.update_data(
        report_id=report.id,
        lang=lang,
        business_unit=bu.value,
        user_telegram_id=user.telegram_id,
    )
    await state.set_state(PurchaseStates.choosing_action)

    await callback.message.edit_text(
        f"🛒 <b>Закуп — {bu_label}</b>\n"
        f"📅 {date.today().strftime('%d.%m.%Y')}\n\n"
        f"Позиций: {entry_count} | Итого: {format_amount(total)} UZS\n\n"
        f"Выберите действие:",
        reply_markup=build_purchase_action_menu(lang, entry_count, total),
    )
    await callback.answer()


# ────────────────────────────────────────────────────────────────────────
# ADD ENTRY — category selection
# ────────────────────────────────────────────────────────────────────────


@router.callback_query(F.data == "pur:add", PurchaseStates.choosing_action)
async def on_add_entry(callback: types.CallbackQuery, state: FSMContext):
    """Show category selection."""
    data = await state.get_data()
    bu = data.get("business_unit", "RESORT")

    await state.set_state(PurchaseStates.choosing_category)
    await callback.message.edit_text(
        "📋 Выберите категорию закупа:",
        reply_markup=build_category_keyboard(bu),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("purcat:"), PurchaseStates.choosing_category)
async def on_category_selected(callback: types.CallbackQuery, state: FSMContext):
    """Category selected — ask for amount."""
    cat_value = callback.data.split(":")[1]
    try:
        cat = PurchaseCategory(cat_value)
        cat_label = PURCHASE_CATEGORY_LABELS.get(cat, cat_value)
    except ValueError:
        await callback.answer("Неверная категория", show_alert=True)
        return

    await state.update_data(category=cat_value, category_label=cat_label)
    await state.set_state(PurchaseStates.entering_amount)

    await callback.message.edit_text(
        f"📋 Категория: <b>{cat_label}</b>\n\n"
        f"💰 Введите сумму:"
    )
    await callback.answer()


@router.callback_query(F.data == "pur:back", PurchaseStates.choosing_category)
async def on_back_from_category(callback: types.CallbackQuery, state: FSMContext):
    """Back to purchase action menu."""
    await _show_action_menu(callback, state)
    await callback.answer()


# ────────────────────────────────────────────────────────────────────────
# AMOUNT ENTRY
# ────────────────────────────────────────────────────────────────────────


@router.message(PurchaseStates.entering_amount)
async def on_amount_entered(message: types.Message, state: FSMContext):
    """Parse purchase amount."""
    raw = message.text.strip().replace(" ", "").replace(",", "").replace(".", "")
    try:
        amount = Decimal(raw)
        if amount <= 0:
            raise ValueError
    except (ValueError, Exception):
        await message.answer("❌ Введите корректную сумму (только цифры)")
        return

    data = await state.get_data()
    await state.update_data(amount=str(amount))
    await state.set_state(PurchaseStates.entering_description)

    await message.answer(
        f"📋 {data['category_label']}\n"
        f"💰 Сумма: {format_amount(amount)} UZS\n\n"
        f"📝 Введите описание (что купили):"
    )


# ────────────────────────────────────────────────────────────────────────
# DESCRIPTION
# ────────────────────────────────────────────────────────────────────────


@router.message(PurchaseStates.entering_description)
async def on_description_entered(message: types.Message, state: FSMContext):
    """Description entered — show confirmation."""
    description = message.text.strip()
    await state.update_data(description=description)
    await state.set_state(PurchaseStates.confirming_entry)

    data = await state.get_data()
    amount = Decimal(data["amount"])

    buttons = [
        [
            InlineKeyboardButton(text="✅ Подтвердить", callback_data="pur:confirm_entry"),
            InlineKeyboardButton(text="❌ Отмена", callback_data="pur:cancel_entry"),
        ]
    ]

    await message.answer(
        f"🛒 <b>Подтверждение закупа</b>\n\n"
        f"📋 {data['category_label']}\n"
        f"💰 Сумма: {format_amount(amount)} UZS\n"
        f"📝 {description}\n\n"
        f"Всё верно?",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
    )


# ────────────────────────────────────────────────────────────────────────
# CONFIRM / CANCEL ENTRY
# ────────────────────────────────────────────────────────────────────────


@router.callback_query(F.data == "pur:confirm_entry", PurchaseStates.confirming_entry)
async def on_confirm_entry(callback: types.CallbackQuery, state: FSMContext):
    """Save purchase entry to report."""
    data = await state.get_data()
    report_id = data["report_id"]
    amount = Decimal(data["amount"])

    async with async_session() as session:
        entry = PurchaseEntry(
            report_id=report_id,
            category=PurchaseCategory(data["category"]),
            amount=amount,
            description=data.get("description", ""),
        )
        session.add(entry)

        # Update report total
        report = await session.get(PurchaseReport, report_id)
        if report:
            report.total_amount = (report.total_amount or Decimal(0)) + amount
        await session.commit()

    await callback.answer("✅ Позиция добавлена")

    # Return to action menu
    await _show_action_menu(callback, state)


@router.callback_query(F.data == "pur:cancel_entry", PurchaseStates.confirming_entry)
async def on_cancel_entry(callback: types.CallbackQuery, state: FSMContext):
    """Cancel entry, back to action menu."""
    await callback.answer("Отменено")
    await _show_action_menu(callback, state)


async def _show_action_menu(callback: types.CallbackQuery, state: FSMContext):
    """Show purchase action menu with current totals."""
    data = await state.get_data()
    report_id = data["report_id"]
    bu = data.get("business_unit", "RESORT")
    bu_label = "Курорт" if bu == "RESORT" else "Ресторан"
    lang = data.get("lang", "ru")

    async with async_session() as session:
        from sqlalchemy.orm import selectinload
        result = await session.execute(
            select(PurchaseReport)
            .where(PurchaseReport.id == report_id)
            .options(selectinload(PurchaseReport.entries))
        )
        report = result.scalar_one()

    entry_count = len(report.entries)
    total = float(report.total_amount or 0)

    await state.set_state(PurchaseStates.choosing_action)
    await callback.message.edit_text(
        f"🛒 <b>Закуп — {bu_label}</b>\n"
        f"📅 {date.today().strftime('%d.%m.%Y')}\n\n"
        f"Позиций: {entry_count} | Итого: {format_amount(total)} UZS\n\n"
        f"Выберите действие:",
        reply_markup=build_purchase_action_menu(lang, entry_count, total),
    )


# ────────────────────────────────────────────────────────────────────────
# PREVIEW
# ────────────────────────────────────────────────────────────────────────


@router.callback_query(F.data == "pur:preview", PurchaseStates.choosing_action)
async def on_preview(callback: types.CallbackQuery, state: FSMContext):
    """Show all entries in the current purchase report."""
    data = await state.get_data()
    report_id = data["report_id"]

    async with async_session() as session:
        from sqlalchemy.orm import selectinload
        result = await session.execute(
            select(PurchaseReport)
            .where(PurchaseReport.id == report_id)
            .options(selectinload(PurchaseReport.entries))
        )
        report = result.scalar_one()

    text = "🛒 <b>Позиции закупа:</b>\n\n"
    for i, entry in enumerate(report.entries, 1):
        cat_label = PURCHASE_CATEGORY_LABELS.get(entry.category, entry.category.value)
        text += (
            f"{i}. <b>{cat_label}</b>\n"
            f"   💰 {format_amount(entry.amount)} UZS — {entry.description}\n\n"
        )
    text += f"<b>Итого: {format_amount(report.total_amount)} UZS</b>"

    buttons = [
        [InlineKeyboardButton(text="◀️ Назад", callback_data="pur:back_to_menu")],
    ]

    await callback.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
    )
    await callback.answer()


@router.callback_query(F.data == "pur:back_to_menu", PurchaseStates.choosing_action)
async def on_back_to_menu(callback: types.CallbackQuery, state: FSMContext):
    """Back to action menu from preview."""
    await _show_action_menu(callback, state)
    await callback.answer()


# ────────────────────────────────────────────────────────────────────────
# FINALIZE — submit report + deduct wallet
# ────────────────────────────────────────────────────────────────────────


@router.callback_query(F.data == "pur:finalize", PurchaseStates.choosing_action)
async def on_finalize(callback: types.CallbackQuery, state: FSMContext):
    """Finalize purchase report — mark SUBMITTED, deduct from wallet."""
    data = await state.get_data()
    report_id = data["report_id"]
    user_tid = data["user_telegram_id"]
    bu = data.get("business_unit", "RESORT")

    report_data = {}
    async with async_session() as session:
        from sqlalchemy.orm import selectinload
        result = await session.execute(
            select(PurchaseReport)
            .where(PurchaseReport.id == report_id)
            .options(selectinload(PurchaseReport.entries))
        )
        report = result.scalar_one_or_none()

        if not report or not report.entries:
            await callback.answer("Нет позиций для отправки", show_alert=True)
            return

        report.status = ReportStatus.SUBMITTED
        total = report.total_amount

        report_data = {
            "total": float(total),
            "count": len(report.entries),
            "bu": report.business_unit.value,
            "date": report.report_date.strftime("%d.%m.%Y"),
        }

        # Create wallet deduction (PURCHASE type)
        wallet_tx = WalletTransaction(
            sender_telegram_id=user_tid,
            amount=total,
            transaction_type=WalletTransactionType.PURCHASE,
            status=WalletTransactionStatus.COMPLETED,
            business_unit=BusinessUnit(bu),
            note=f"Закуп {report_data['date']} ({report_data['count']} поз.)",
        )
        session.add(wallet_tx)
        await session.commit()

    await state.clear()
    await callback.answer()

    # Show success
    user = await get_user(callback.from_user.id)
    if user:
        lang = user.language.value.lower()
        section = user.active_section.value.lower()
        section_name = get_text(f"section_{section}", lang)
        await callback.message.edit_text(
            f"✅ Закуп отправлен!\n"
            f"💰 {format_amount(report_data['total'])} UZS ({report_data['count']} поз.)\n\n"
            f"{get_text('main_menu', lang, section=section_name)}",
            reply_markup=main_menu_keyboard(lang, current_section=section, role=user.role.value),
        )

        # Notify owners (fire-and-forget)
        bu_label = "Курорт" if bu == "RESORT" else "Ресторан"
        entries_text = ""
        async with async_session() as session:
            from sqlalchemy.orm import selectinload
            result = await session.execute(
                select(PurchaseReport)
                .where(PurchaseReport.id == report_id)
                .options(selectinload(PurchaseReport.entries))
            )
            rpt = result.scalar_one_or_none()
            if rpt:
                for e in rpt.entries:
                    cat_label = PURCHASE_CATEGORY_LABELS.get(e.category, e.category.value)
                    entries_text += f"  • {cat_label}: {format_amount(e.amount)} UZS — {e.description}\n"

        notify_owners(
            callback.bot,
            f"🛒 <b>Новый закуп</b>\n\n"
            f"👤 {user.full_name}\n"
            f"🏢 {bu_label}\n"
            f"📅 {report_data['date']}\n\n"
            f"{entries_text}\n"
            f"💰 <b>Итого: {format_amount(report_data['total'])} UZS</b>",
        )


# ────────────────────────────────────────────────────────────────────────
# CANCEL
# ────────────────────────────────────────────────────────────────────────


@router.callback_query(F.data == "pur:cancel")
async def on_cancel(callback: types.CallbackQuery, state: FSMContext):
    """Cancel purchase — back to main menu. Draft stays in DB."""
    await state.clear()

    user = await get_user(callback.from_user.id)
    if user:
        lang = user.language.value.lower()
        section = user.active_section.value.lower()
        section_name = get_text(f"section_{section}", lang)
        await callback.message.edit_text(
            f"❌ Отменено\n\n{get_text('main_menu', lang, section=section_name)}",
            reply_markup=main_menu_keyboard(lang, current_section=section, role=user.role.value),
        )
    await callback.answer()
