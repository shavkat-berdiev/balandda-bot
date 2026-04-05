"""Expense entry handler for structured reports.

Flow:
1. Entry: callback "rpt:add_expense" from report action menu
2. Show expense categories
3. If KITCHEN/STAFF/INKASSATSIYA: show staff member selection
4. Ask amount
5. Ask description (optional)
6. Confirm → save ExpenseEntry → return to report menu
"""

import logging
from decimal import Decimal

from aiogram import F, Router, types
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import select

from bot.locales import get_text
from db.database import async_session
from db.enums import (
    ExpenseCategory,
    EXPENSE_CATEGORY_LABELS,
)
from db.models import (
    ExpenseEntry,
    StaffMember,
    StructuredReport,
    User,
)

router = Router()
logger = logging.getLogger(__name__)


class ExpenseStates(StatesGroup):
    """FSM states for expense entry."""
    choosing_category = State()
    choosing_staff = State()
    entering_amount = State()
    entering_description = State()
    confirming = State()


async def get_user(telegram_id: int) -> User | None:
    """Get user from database."""
    async with async_session() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == telegram_id)
        )
        return result.scalar_one_or_none()


def format_amount(amount: float | Decimal) -> str:
    """Format amount with dot separators (e.g., 3.200.000)."""
    if isinstance(amount, Decimal):
        amount = float(amount)
    return f"{amount:,.0f}".replace(",", ".")


async def build_category_keyboard(lang: str) -> InlineKeyboardMarkup:
    """Build expense category selection keyboard."""
    buttons = []
    for category in ExpenseCategory:
        # INKASSATSIYA replaced by wallet transfers
        if category == ExpenseCategory.INKASSATSIYA:
            continue
        label = EXPENSE_CATEGORY_LABELS.get(category, category.value)
        buttons.append([InlineKeyboardButton(text=label, callback_data=f"exp_cat:{category.value}")])

    buttons.append([InlineKeyboardButton(text=f"❌ {get_text('btn_cancel', lang)}", callback_data="exp:cancel")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


async def build_staff_keyboard(lang: str) -> InlineKeyboardMarkup:
    """Build staff member selection keyboard."""
    async with async_session() as session:
        result = await session.execute(
            select(StaffMember).where(StaffMember.is_active == True)
        )
        staff_members = result.scalars().all()

    buttons = []
    for member in staff_members:
        buttons.append([InlineKeyboardButton(text=member.name, callback_data=f"exp_staff:{member.id}")])

    buttons.append([InlineKeyboardButton(text="Пропустить", callback_data="exp_staff:none")])
    buttons.append([InlineKeyboardButton(text=f"❌ {get_text('btn_cancel', lang)}", callback_data="exp:cancel")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


# ────────────────────────────────────────────────────────────────────────
# ENTRY POINT
# ────────────────────────────────────────────────────────────────────────


@router.callback_query(F.data == "rpt:add_expense")
async def on_add_expense(callback: types.CallbackQuery, state: FSMContext):
    """Start expense entry flow."""
    user = await get_user(callback.from_user.id)
    if not user:
        await callback.answer("Пользователь не найден")
        return

    lang = user.language.value.lower()

    # Get report_id from state if in report flow, otherwise create context
    data = await state.get_data()
    if "report_id" not in data:
        # Standalone expense entry - need to initialize
        await state.update_data(lang=lang, user_id=user.id)

    await state.set_state(ExpenseStates.choosing_category)
    keyboard = await build_category_keyboard(lang)

    await callback.message.edit_text(
        "💸 Выберите категорию расхода:",
        reply_markup=keyboard,
    )
    await callback.answer()


# ────────────────────────────────────────────────────────────────────────
# STEP 1: CATEGORY SELECTION
# ────────────────────────────────────────────────────────────────────────


@router.callback_query(F.data.startswith("exp_cat:"), ExpenseStates.choosing_category)
async def on_category_selected(callback: types.CallbackQuery, state: FSMContext):
    """Expense category selected."""
    category_str = callback.data.split(":")[1]
    category = ExpenseCategory(category_str)
    data = await state.get_data()
    lang = data.get("lang", "ru")

    await state.update_data(expense_category=category_str)

    # Check if category requires staff selection
    staff_required_categories = [
        ExpenseCategory.KITCHEN.value,
        ExpenseCategory.STAFF.value,
        ExpenseCategory.INKASSATSIYA.value,
    ]

    if category_str in staff_required_categories:
        await state.set_state(ExpenseStates.choosing_staff)
        keyboard = await build_staff_keyboard(lang)
        await callback.message.edit_text(
            f"👤 {EXPENSE_CATEGORY_LABELS.get(category, category.value)}\n\n"
            f"Выберите сотрудника (или пропустите):",
            reply_markup=keyboard,
        )
    else:
        # Skip staff selection, go directly to amount
        await _ask_for_amount(callback.message, state)

    await callback.answer()


# ────────────────────────────────────────────────────────────────────────
# STEP 2: STAFF SELECTION (optional)
# ────────────────────────────────────────────────────────────────────────


@router.callback_query(F.data.startswith("exp_staff:"), ExpenseStates.choosing_staff)
async def on_staff_selected(callback: types.CallbackQuery, state: FSMContext):
    """Staff member selected or skipped."""
    staff_id_str = callback.data.split(":")[1]

    if staff_id_str != "none":
        staff_id = int(staff_id_str)
        await state.update_data(staff_member_id=staff_id)

    # Move to amount entry
    await _ask_for_amount(callback.message, state)
    await callback.answer()


async def _ask_for_amount(message: types.Message, state: FSMContext):
    """Helper to ask for expense amount."""
    data = await state.get_data()
    lang = data.get("lang", "ru")

    await state.set_state(ExpenseStates.entering_amount)
    await message.edit_text(
        "💰 Введите размер расхода (сумма в UZS):"
    )


# ────────────────────────────────────────────────────────────────────────
# STEP 3: AMOUNT ENTRY
# ────────────────────────────────────────────────────────────────────────


@router.message(ExpenseStates.entering_amount)
async def on_amount_entered(message: types.Message, state: FSMContext):
    """Expense amount entered."""
    data = await state.get_data()
    lang = data.get("lang", "ru")

    # Parse amount
    raw = message.text.strip().replace(" ", "").replace(",", "").replace(".", "")
    try:
        amount = Decimal(raw)
        if amount <= 0:
            raise ValueError
    except (ValueError, Exception):
        await message.answer("❌ Введите корректную сумму (только цифры)")
        return

    await state.update_data(amount=str(amount))
    await _ask_for_description(message, state)


async def _ask_for_description(message: types.Message, state: FSMContext):
    """Helper to ask for expense description."""
    data = await state.get_data()
    lang = data.get("lang", "ru")

    buttons = [
        [InlineKeyboardButton(text="⏩ Пропустить", callback_data="exp_desc:skip")],
        [InlineKeyboardButton(text=f"❌ {get_text('btn_cancel', lang)}", callback_data="exp:cancel")],
    ]

    await state.set_state(ExpenseStates.entering_description)
    await message.answer(
        "📝 Добавьте описание расхода (или пропустите):",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
    )


# ────────────────────────────────────────────────────────────────────────
# STEP 4: DESCRIPTION (optional)
# ────────────────────────────────────────────────────────────────────────


@router.callback_query(F.data == "exp_desc:skip", ExpenseStates.entering_description)
async def on_description_skip(callback: types.CallbackQuery, state: FSMContext):
    """Description skipped."""
    await state.update_data(description="")
    await _show_confirmation(callback.message, state, edit=True)
    await callback.answer()


@router.message(ExpenseStates.entering_description)
async def on_description_entered(message: types.Message, state: FSMContext):
    """Description entered."""
    description = message.text.strip()
    await state.update_data(description=description)
    await _show_confirmation(message, state, edit=False)


async def _show_confirmation(message: types.Message, state: FSMContext, edit: bool = False):
    """Helper to show expense confirmation."""
    data = await state.get_data()
    lang = data.get("lang", "ru")

    category = ExpenseCategory(data["expense_category"])
    category_label = EXPENSE_CATEGORY_LABELS.get(category, category.value)
    amount = Decimal(data["amount"])
    description = data.get("description", "")

    # Get staff name if selected
    staff_name = ""
    if data.get("staff_member_id"):
        async with async_session() as session:
            result = await session.execute(
                select(StaffMember).where(StaffMember.id == data["staff_member_id"])
            )
            staff = result.scalar_one_or_none()
            if staff:
                staff_name = f"\nСотрудник: {staff.name}"

    summary = (
        f"📝 Подтверждение расхода\n\n"
        f"Категория: {category_label}\n"
        f"Сумма: {format_amount(amount)}\n"
    )

    if staff_name:
        summary += staff_name + "\n"

    if description:
        summary += f"Описание: {description}\n"

    summary += "\nВсё верно?"

    buttons = [
        [
            InlineKeyboardButton(text="✅ Подтвердить", callback_data="exp:confirm"),
            InlineKeyboardButton(text="❌ Отмена", callback_data="exp:cancel"),
        ]
    ]

    await state.set_state(ExpenseStates.confirming)

    if edit:
        await message.edit_text(summary, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    else:
        await message.answer(summary, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))


# ────────────────────────────────────────────────────────────────────────
# STEP 5: CONFIRM & SAVE
# ────────────────────────────────────────────────────────────────────────


@router.callback_query(F.data == "exp:confirm", ExpenseStates.confirming)
async def on_confirm_expense(callback: types.CallbackQuery, state: FSMContext):
    """Save expense entry."""
    data = await state.get_data()
    lang = data.get("lang", "ru")
    report_id = data.get("report_id")

    if not report_id:
        await callback.answer("Ошибка: отчёт не найден")
        return

    async with async_session() as session:
        # Create ExpenseEntry
        entry = ExpenseEntry(
            report_id=report_id,
            expense_category=ExpenseCategory(data["expense_category"]),
            staff_member_id=data.get("staff_member_id"),
            amount=Decimal(data["amount"]),
            description=data.get("description", ""),
        )
        session.add(entry)

        # Update report totals
        report = await session.get(StructuredReport, report_id)
        if report:
            report.total_expense = (report.total_expense or Decimal(0)) + Decimal(data["amount"])
            await session.merge(report)

        await session.commit()

    await callback.answer("✅ Расход добавлен")

    # Return to report menu or main menu
    if data.get("report_id"):
        # In report flow - go back to report action menu
        from bot.handlers.new_report import build_report_action_menu

        bu = data.get("business_unit", "RESORT")
        keyboard = await build_report_action_menu(lang, business_unit=bu)
        await callback.message.edit_text(
            "✅ Расход добавлен\n\nВыберите действие:",
            reply_markup=keyboard,
        )
    else:
        # Standalone - go back to main menu
        user = await get_user(callback.from_user.id)
        if user:
            from bot.keyboards.main import main_menu_keyboard

            section = user.active_section.value.lower()
            section_name = get_text(f"section_{section}", lang)
            await callback.message.edit_text(
                f"✅ Расход добавлен\n\n{get_text('main_menu', lang, section=section_name)}",
                reply_markup=main_menu_keyboard(lang, current_section=section),
            )


# ────────────────────────────────────────────────────────────────────────
# CANCEL
# ────────────────────────────────────────────────────────────────────────


@router.callback_query(F.data == "exp:cancel")
async def on_cancel_expense(callback: types.CallbackQuery, state: FSMContext):
    """Cancel expense entry."""
    data = await state.get_data()
    lang = data.get("lang", "ru")

    await state.clear()

    # Return to report menu or main menu
    if data.get("report_id"):
        # In report flow - go back to report action menu
        from bot.handlers.new_report import build_report_action_menu, NewReportStates

        bu = data.get("business_unit", "RESORT")
        await state.update_data(
            report_id=data["report_id"], lang=lang,
            user_id=data.get("user_id"), business_unit=bu,
            report_date=data.get("report_date"),
        )
        await state.set_state(NewReportStates.choosing_action)

        keyboard = await build_report_action_menu(lang, business_unit=bu)
        await callback.message.edit_text(
            "❌ Отменено\n\nВыберите действие:",
            reply_markup=keyboard,
        )
    else:
        # Standalone - go back to main menu
        user = await get_user(callback.from_user.id)
        if user:
            from bot.keyboards.main import main_menu_keyboard

            section = user.active_section.value.lower()
            section_name = get_text(f"section_{section}", lang)
            await callback.message.edit_text(
                f"❌ Отменено\n\n{get_text('main_menu', lang, section=section_name)}",
                reply_markup=main_menu_keyboard(lang, current_section=section),
            )

    await callback.answer()
