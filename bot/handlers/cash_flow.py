"""Cash-in and cash-out handlers with conversation flow:
1. User taps Приход/Расход button
2. Bot shows category selection
3. User enters amount
4. User optionally adds a note
5. User confirms → transaction saved
"""

import logging
from decimal import Decimal, InvalidOperation

from aiogram import F, Router, types
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import select

from bot.keyboards.main import main_menu_keyboard
from bot.locales import get_text
from db.database import async_session
from db.models import (
    BusinessUnit,
    Category,
    Transaction,
    TransactionType,
    User,
)

router = Router()
logger = logging.getLogger(__name__)


class CashFlowStates(StatesGroup):
    waiting_for_amount = State()
    waiting_for_note = State()
    waiting_for_confirm = State()


async def get_user(telegram_id: int) -> User | None:
    async with async_session() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == telegram_id)
        )
        return result.scalar_one_or_none()


async def build_category_keyboard(
    business_unit: BusinessUnit, transaction_type: TransactionType, lang: str
) -> InlineKeyboardMarkup:
    """Build inline keyboard with categories for the given business unit and type."""
    async with async_session() as session:
        result = await session.execute(
            select(Category)
            .where(
                Category.business_unit == business_unit,
                Category.transaction_type == transaction_type,
                Category.is_active == True,
            )
            .order_by(Category.sort_order)
        )
        categories = result.scalars().all()

    buttons = []
    for cat in categories:
        name = cat.name_uz if lang == "uz" else cat.name_ru
        buttons.append(
            [InlineKeyboardButton(text=name, callback_data=f"cat:{cat.id}")]
        )

    buttons.append(
        [InlineKeyboardButton(text=f"❌ {get_text('btn_cancel', lang)}", callback_data="cash:cancel")]
    )
    return InlineKeyboardMarkup(inline_keyboard=buttons)


# --- Entry points: Приход / Расход buttons ---

@router.callback_query(F.data == "action:cash_in")
async def on_cash_in(callback: types.CallbackQuery, state: FSMContext):
    """Start cash-in flow."""
    user = await get_user(callback.from_user.id)
    if not user:
        await callback.answer()
        return

    lang = user.language.value.lower()
    keyboard = await build_category_keyboard(
        user.active_section, TransactionType.CASH_IN, lang
    )

    await state.update_data(
        transaction_type=TransactionType.CASH_IN.value,
        business_unit=user.active_section.value.lower(),
        lang=lang,
    )

    await callback.message.edit_text(
        f"💰 {get_text('btn_cash_in', lang)}\n\n{get_text('select_category', lang)}",
        reply_markup=keyboard,
    )
    await callback.answer()


@router.callback_query(F.data == "action:cash_out")
async def on_cash_out(callback: types.CallbackQuery, state: FSMContext):
    """Start cash-out flow."""
    user = await get_user(callback.from_user.id)
    if not user:
        await callback.answer()
        return

    lang = user.language.value.lower()
    keyboard = await build_category_keyboard(
        user.active_section, TransactionType.CASH_OUT, lang
    )

    await state.update_data(
        transaction_type=TransactionType.CASH_OUT.value,
        business_unit=user.active_section.value.lower(),
        lang=lang,
    )

    await callback.message.edit_text(
        f"💸 {get_text('btn_cash_out', lang)}\n\n{get_text('select_category', lang)}",
        reply_markup=keyboard,
    )
    await callback.answer()


# --- Step 2: Category selected → ask for amount ---

@router.callback_query(F.data.startswith("cat:"))
async def on_category_select(callback: types.CallbackQuery, state: FSMContext):
    """User selected a category, now ask for amount."""
    category_id = int(callback.data.split(":")[1])
    data = await state.get_data()
    lang = data.get("lang", "ru")

    # Get category name for display
    async with async_session() as session:
        result = await session.execute(select(Category).where(Category.id == category_id))
        category = result.scalar_one_or_none()

    if not category:
        await callback.answer("Category not found")
        return

    cat_name = category.name_uz if lang == "uz" else category.name_ru
    await state.update_data(category_id=category_id, category_name=cat_name)
    await state.set_state(CashFlowStates.waiting_for_amount)

    await callback.message.edit_text(
        f"📂 {cat_name}\n\n{get_text('enter_amount', lang)}"
    )
    await callback.answer()


# --- Step 3: Amount entered → ask for note ---

@router.message(CashFlowStates.waiting_for_amount)
async def on_amount_entered(message: types.Message, state: FSMContext):
    """User entered amount, validate and ask for note."""
    data = await state.get_data()
    lang = data.get("lang", "ru")

    # Parse amount — accept formats like "50000", "50 000", "1,500,000"
    raw = message.text.strip().replace(" ", "").replace(",", "").replace(".", "")

    try:
        amount = Decimal(raw)
        if amount <= 0:
            raise InvalidOperation
    except (InvalidOperation, ValueError):
        await message.answer(get_text("invalid_amount", lang))
        return

    await state.update_data(amount=str(amount))

    cancel_kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text=f"⏩ {get_text('btn_skip', lang)}",
                callback_data="note:skip",
            ),
            InlineKeyboardButton(
                text=f"❌ {get_text('btn_cancel', lang)}",
                callback_data="cash:cancel",
            ),
        ]
    ])

    await state.set_state(CashFlowStates.waiting_for_note)
    await message.answer(get_text("enter_note", lang), reply_markup=cancel_kb)


# --- Step 3b: Skip note ---

@router.callback_query(F.data == "note:skip", CashFlowStates.waiting_for_note)
async def on_note_skip(callback: types.CallbackQuery, state: FSMContext):
    """User skipped the note."""
    await state.update_data(note="-")
    await _show_confirmation(callback.message, state, edit=True)
    await callback.answer()


# --- Step 4: Note entered → show confirmation ---

@router.message(CashFlowStates.waiting_for_note)
async def on_note_entered(message: types.Message, state: FSMContext):
    """User entered a note."""
    note = message.text.strip()
    if message.text == "/skip":
        note = "-"
    await state.update_data(note=note)
    await _show_confirmation(message, state, edit=False)


async def _show_confirmation(message: types.Message, state: FSMContext, edit: bool = False):
    """Show transaction summary for confirmation."""
    data = await state.get_data()
    lang = data.get("lang", "ru")
    tx_type = data["transaction_type"]
    amount = Decimal(data["amount"])

    type_label = get_text("btn_cash_in" if tx_type.upper() == "CASH_IN" else "btn_cash_out", lang)
    note = data.get("note", "-")

    confirm_kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text=f"✅ {get_text('btn_confirm', lang)}",
                callback_data="cash:confirm",
            ),
            InlineKeyboardButton(
                text=f"❌ {get_text('btn_cancel', lang)}",
                callback_data="cash:cancel",
            ),
        ]
    ])

    text = get_text(
        "confirm_transaction",
        lang,
        type=type_label,
        amount=float(amount),
        category=data["category_name"],
        note=note,
    )

    await state.set_state(CashFlowStates.waiting_for_confirm)

    if edit:
        await message.edit_text(text, reply_markup=confirm_kb)
    else:
        await message.answer(text, reply_markup=confirm_kb)


# --- Step 5: Confirm → save transaction ---

@router.callback_query(F.data == "cash:confirm", CashFlowStates.waiting_for_confirm)
async def on_confirm(callback: types.CallbackQuery, state: FSMContext):
    """Save the transaction to database."""
    data = await state.get_data()
    lang = data.get("lang", "ru")

    async with async_session() as session:
        # Get user
        result = await session.execute(
            select(User).where(User.telegram_id == callback.from_user.id)
        )
        user = result.scalar_one_or_none()
        if not user:
            await callback.answer()
            await state.clear()
            return

        transaction = Transaction(
            user_id=user.id,
            category_id=data["category_id"],
            business_unit=BusinessUnit(data["business_unit"].upper()),
            transaction_type=TransactionType(data["transaction_type"].upper()),
            amount=Decimal(data["amount"]),
            note=data.get("note") if data.get("note") != "-" else None,
        )
        session.add(transaction)
        await session.commit()

    await state.clear()

    # Show success + return to main menu
    section_name = get_text(f"section_{data['business_unit']}", lang)
    await callback.message.edit_text(
        f"✅ {get_text('transaction_saved', lang)}\n\n"
        f"{get_text('main_menu', lang, section=section_name)}",
        reply_markup=main_menu_keyboard(lang),
    )
    await callback.answer(get_text("transaction_saved", lang))


# --- Cancel at any point ---

@router.callback_query(F.data == "cash:cancel")
async def on_cancel(callback: types.CallbackQuery, state: FSMContext):
    """Cancel the current flow and return to main menu."""
    await state.clear()

    user = await get_user(callback.from_user.id)
    if not user:
        await callback.answer()
        return

    lang = user.language.value.lower()
    section_name = get_text(f"section_{user.active_section.value.lower()}", lang)

    await callback.message.edit_text(
        f"{get_text('transaction_cancelled', lang)}\n\n"
        f"{get_text('main_menu', lang, section=section_name)}",
        reply_markup=main_menu_keyboard(lang),
    )
    await callback.answer()
