"""XUSH business unit — simplified cash-box workflow.

Menu: Касса (wallet) | Расходы (4 categories) | Инкассация (to Akbar/Shavkat)
All amounts deduct from the user's wallet (same as other sections).
"""

import logging
from decimal import Decimal

from aiogram import F, Router, types
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import select

from bot.keyboards.main import main_menu_keyboard
from bot.locales import get_text
from bot.notifications import notify_wallet_transfer
from db.database import async_session
from db.enums import (
    UserRole,
    WalletTransactionType,
    WalletTransactionStatus,
    WALLET_TRANSACTION_TYPE_LABELS,
)
from db.models import User, WalletTransaction

router = Router()
logger = logging.getLogger(__name__)

# ── XUSH expense categories ──
XUSH_EXPENSE_CATEGORIES = [
    ("transport", "🚗 Транспорт"),
    ("food", "🍽 Питание"),
    ("stationary", "📎 Канцелярия"),
    ("salary", "💰 Зарплата"),
]


class XushStates(StatesGroup):
    choosing_expense_cat = State()
    entering_expense_amount = State()
    entering_expense_note = State()
    choosing_transfer_recipient = State()
    entering_transfer_amount = State()
    entering_transfer_note = State()
    confirming_transfer = State()


def format_amount(amount: float | Decimal) -> str:
    if isinstance(amount, Decimal):
        amount = float(amount)
    return f"{amount:,.0f}".replace(",", ".")


# ────────────────────────────────────────────────────────────────────────
# EXPENSES — 4 simple categories
# ────────────────────────────────────────────────────────────────────────


@router.callback_query(F.data == "xush:expenses")
async def on_xush_expenses(callback: types.CallbackQuery, state: FSMContext):
    """Show XUSH expense categories."""
    buttons = []
    for code, label in XUSH_EXPENSE_CATEGORIES:
        buttons.append([InlineKeyboardButton(
            text=label, callback_data=f"xush_exp:{code}",
        )])
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="xush:back_menu")])

    await state.set_state(XushStates.choosing_expense_cat)
    await callback.message.edit_text(
        "📤 <b>Расходы XUSH</b>\n\nВыберите категорию:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("xush_exp:"), XushStates.choosing_expense_cat)
async def on_xush_expense_cat(callback: types.CallbackQuery, state: FSMContext):
    """Category selected — ask for amount."""
    cat_code = callback.data.split(":")[1]
    cat_label = next((l for c, l in XUSH_EXPENSE_CATEGORIES if c == cat_code), cat_code)

    # Get balance
    from bot.handlers.wallet import get_wallet_balance
    balance = await get_wallet_balance(callback.from_user.id)

    await state.update_data(
        xush_exp_cat=cat_code,
        xush_exp_label=cat_label,
    )
    await state.set_state(XushStates.entering_expense_amount)
    await callback.message.edit_text(
        f"{cat_label}\n\n"
        f"💰 Баланс кассы: <b>{format_amount(balance)} UZS</b>\n\n"
        f"Введите сумму расхода:",
    )
    await callback.answer()


@router.message(XushStates.entering_expense_amount)
async def on_xush_expense_amount(message: types.Message, state: FSMContext):
    """Parse amount, ask for optional note."""
    text = message.text.strip().replace(" ", "").replace(".", "").replace(",", "")
    if not text.isdigit() or int(text) <= 0:
        await message.answer("Введите корректную сумму (только цифры).")
        return

    await state.update_data(xush_exp_amount=text)
    await state.set_state(XushStates.entering_expense_note)
    await message.answer(
        f"Сумма: <b>{format_amount(int(text))} UZS</b>\n\n"
        f"Добавьте комментарий (или нажмите /skip):",
    )


@router.message(XushStates.entering_expense_note)
async def on_xush_expense_note(message: types.Message, state: FSMContext):
    """Save expense as wallet EXPENSE transaction."""
    data = await state.get_data()
    note = "" if message.text.strip() == "/skip" else message.text.strip()
    amount = Decimal(data["xush_exp_amount"])
    cat_label = data["xush_exp_label"]
    cat_code = data["xush_exp_cat"]

    # Determine transaction type
    tx_type = WalletTransactionType.SALARY if cat_code == "salary" else WalletTransactionType.EXPENSE

    async with async_session() as session:
        session.add(WalletTransaction(
            sender_telegram_id=message.from_user.id,
            amount=amount,
            transaction_type=tx_type,
            status=WalletTransactionStatus.COMPLETED,
            note=note or cat_label,
            business_unit="XUSH",
        ))
        await session.commit()

    await state.clear()

    # Get updated balance
    from bot.handlers.wallet import get_wallet_balance
    balance = await get_wallet_balance(message.from_user.id)

    # Get user for menu
    async with async_session() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == message.from_user.id)
        )
        user = result.scalar_one_or_none()

    lang = user.language.value.lower() if user else "ru"
    section = user.active_section.value.lower() if user else "xush"
    section_name = get_text(f"section_{section}", lang)

    await message.answer(
        f"✅ Расход записан: {cat_label}\n"
        f"Сумма: -{format_amount(amount)} UZS\n"
        f"💰 Баланс кассы: <b>{format_amount(balance)} UZS</b>\n\n"
        f"{get_text('main_menu', lang, section=section_name)}",
        reply_markup=main_menu_keyboard(lang, current_section=section, role=user.role.value if user else ""),
    )


# ────────────────────────────────────────────────────────────────────────
# TRANSFER (ИНКАССАЦИЯ) — only to specific people
# ────────────────────────────────────────────────────────────────────────


@router.callback_query(F.data == "xush:transfer")
async def on_xush_transfer(callback: types.CallbackQuery, state: FSMContext):
    """Show transfer recipients — only OWNER + ADMIN users."""
    async with async_session() as session:
        result = await session.execute(
            select(User).where(
                User.is_active == True,
                User.telegram_id != callback.from_user.id,
                User.role.in_([UserRole.OWNER, UserRole.ADMIN]),
            ).order_by(User.full_name)
        )
        recipients = result.scalars().all()

    if not recipients:
        await callback.answer("Нет доступных получателей", show_alert=True)
        return

    # Get balance
    from bot.handlers.wallet import get_wallet_balance
    balance = await get_wallet_balance(callback.from_user.id)

    buttons = []
    for u in recipients:
        role_icon = "👑" if u.role == UserRole.OWNER else "👤"
        buttons.append([InlineKeyboardButton(
            text=f"{role_icon} {u.full_name}",
            callback_data=f"xush_tr:{u.telegram_id}",
        )])
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="xush:back_menu")])

    await state.update_data(
        xush_sender_tid=callback.from_user.id,
    )
    await state.set_state(XushStates.choosing_transfer_recipient)
    await callback.message.edit_text(
        f"💼 <b>Инкассация XUSH</b>\n\n"
        f"💰 Баланс кассы: <b>{format_amount(balance)} UZS</b>\n\n"
        f"Выберите получателя:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("xush_tr:"), XushStates.choosing_transfer_recipient)
async def on_xush_recipient_selected(callback: types.CallbackQuery, state: FSMContext):
    """Recipient selected — ask for amount."""
    receiver_tid = int(callback.data.split(":")[1])

    async with async_session() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == receiver_tid)
        )
        receiver = result.scalar_one_or_none()

    receiver_name = receiver.full_name if receiver else "?"
    await state.update_data(
        xush_receiver_tid=receiver_tid,
        xush_receiver_name=receiver_name,
    )

    from bot.handlers.wallet import get_wallet_balance
    balance = await get_wallet_balance(callback.from_user.id)

    await state.set_state(XushStates.entering_transfer_amount)
    await callback.message.edit_text(
        f"👤 Получатель: <b>{receiver_name}</b>\n"
        f"💰 Баланс кассы: {format_amount(balance)} UZS\n\n"
        f"Введите сумму перевода:",
    )
    await callback.answer()


@router.message(XushStates.entering_transfer_amount)
async def on_xush_transfer_amount(message: types.Message, state: FSMContext):
    """Parse amount, ask for note."""
    text = message.text.strip().replace(" ", "").replace(".", "").replace(",", "")
    if not text.isdigit() or int(text) <= 0:
        await message.answer("Введите корректную сумму (только цифры).")
        return

    from bot.handlers.wallet import get_wallet_balance
    balance = await get_wallet_balance(message.from_user.id)
    amount = Decimal(text)

    if amount > balance:
        await message.answer(
            f"❌ Недостаточно средств.\n"
            f"Баланс: {format_amount(balance)} UZS\n"
            f"Запрошено: {format_amount(amount)} UZS",
        )
        return

    data = await state.get_data()
    await state.update_data(xush_transfer_amount=text)
    await state.set_state(XushStates.entering_transfer_note)
    await message.answer(
        f"👤 Получатель: <b>{data['xush_receiver_name']}</b>\n"
        f"💰 Сумма: <b>{format_amount(amount)} UZS</b>\n\n"
        f"Добавьте комментарий (или /skip):",
    )


@router.message(XushStates.entering_transfer_note)
async def on_xush_transfer_note(message: types.Message, state: FSMContext):
    """Show confirmation."""
    note = "" if message.text.strip() == "/skip" else message.text.strip()
    data = await state.get_data()
    await state.update_data(xush_transfer_note=note)

    amount = Decimal(data["xush_transfer_amount"])
    await state.set_state(XushStates.confirming_transfer)
    await message.answer(
        f"💼 <b>Подтвердите перевод</b>\n\n"
        f"👤 Получатель: {data['xush_receiver_name']}\n"
        f"💰 Сумма: <b>{format_amount(amount)} UZS</b>\n"
        f"{'📝 ' + note if note else ''}\n\n"
        f"Подтвердить?",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Подтвердить", callback_data="xush:confirm_transfer"),
                InlineKeyboardButton(text="❌ Отмена", callback_data="xush:back_menu"),
            ],
        ]),
    )


@router.callback_query(F.data == "xush:confirm_transfer", XushStates.confirming_transfer)
async def on_xush_confirm_transfer(callback: types.CallbackQuery, state: FSMContext):
    """Create PENDING transfer transaction."""
    data = await state.get_data()
    amount = Decimal(data["xush_transfer_amount"])
    receiver_tid = data["xush_receiver_tid"]
    receiver_name = data["xush_receiver_name"]
    note = data.get("xush_transfer_note", "")

    async with async_session() as session:
        tx = WalletTransaction(
            sender_telegram_id=callback.from_user.id,
            receiver_telegram_id=receiver_tid,
            amount=amount,
            transaction_type=WalletTransactionType.TRANSFER_TO_EMPLOYEE,
            status=WalletTransactionStatus.PENDING,
            note=note or "Инкассация XUSH",
            business_unit="XUSH",
        )
        session.add(tx)
        await session.commit()
        tx_id = tx.id

    await state.clear()
    await callback.answer()

    # Get sender name
    async with async_session() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == callback.from_user.id)
        )
        sender = result.scalar_one_or_none()

    sender_name = sender.full_name if sender else "?"

    # Send accept/decline to receiver
    try:
        await callback.bot.send_message(
            receiver_tid,
            f"📥 <b>Входящий перевод (XUSH)</b>\n\n"
            f"👤 Отправитель: {sender_name}\n"
            f"💰 Сумма: <b>{format_amount(amount)} UZS</b>\n"
            f"{'📝 ' + note if note else ''}\n\n"
            f"Подтвердите получение:",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(text="✅ Принять", callback_data=f"wlt_accept:{tx_id}"),
                    InlineKeyboardButton(text="❌ Отклонить", callback_data=f"wlt_decline:{tx_id}"),
                ]
            ]),
        )
    except Exception as e:
        logger.error(f"Failed to send XUSH transfer to {receiver_tid}: {e}")

    # Notify owners
    await notify_wallet_transfer(
        callback.bot, sender_name, "Инкассация XUSH ⏳",
        receiver_name, float(amount), note,
        exclude_tid=receiver_tid,
    )

    # Show confirmation to sender
    lang = sender.language.value.lower() if sender else "ru"
    section = sender.active_section.value.lower() if sender else "xush"
    section_name = get_text(f"section_{section}", lang)

    await callback.message.edit_text(
        f"⏳ Перевод: {format_amount(amount)} UZS → {receiver_name}\n"
        f"Ожидает подтверждения\n\n"
        f"{get_text('main_menu', lang, section=section_name)}",
        reply_markup=main_menu_keyboard(lang, current_section=section, role=sender.role.value if sender else ""),
    )


# ────────────────────────────────────────────────────────────────────────
# BACK TO MENU
# ────────────────────────────────────────────────────────────────────────


@router.callback_query(F.data == "xush:back_menu")
async def on_xush_back_menu(callback: types.CallbackQuery, state: FSMContext):
    """Return to XUSH main menu."""
    await state.clear()

    async with async_session() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == callback.from_user.id)
        )
        user = result.scalar_one_or_none()

    lang = user.language.value.lower() if user else "ru"
    section = user.active_section.value.lower() if user else "xush"
    section_name = get_text(f"section_{section}", lang)

    await callback.message.edit_text(
        get_text("main_menu", lang, section=section_name),
        reply_markup=main_menu_keyboard(lang, current_section=section, role=user.role.value if user else ""),
    )
    await callback.answer()
