"""Wallet handler — cash balance tracking and transfers.

Flow:
1. User taps "💰 Кошелёк" → show balance + action buttons
2. Actions: Transfer to employee, Transfer to Shavkat, Cash to bank
3. Transfer flow: select recipient → enter amount → optional note → confirm
4. Auto CASH_IN happens in new_report.py when cash income is saved
"""

import logging
from decimal import Decimal

from aiogram import Bot, F, Router, types
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import select, func, case, or_

from bot.config import settings
from bot.keyboards.main import main_menu_keyboard
from bot.locales import get_text
from db.database import async_session
from db.enums import UserRole, WalletTransactionType, WALLET_TRANSACTION_TYPE_LABELS
from db.models import User, WalletTransaction

router = Router()
logger = logging.getLogger(__name__)


class WalletStates(StatesGroup):
    viewing = State()
    choosing_recipient = State()
    entering_amount = State()
    entering_note = State()
    confirming = State()


def format_amount(amount: float | Decimal) -> str:
    """Format amount with dot separators (e.g., 3.200.000)."""
    if isinstance(amount, Decimal):
        amount = float(amount)
    return f"{amount:,.0f}".replace(",", ".")


async def get_wallet_balance(telegram_id: int) -> Decimal:
    """Calculate current wallet balance for a user.

    Balance = SUM(CASH_IN) + SUM(received transfers) - SUM(sent transfers) - SUM(final destinations)
    """
    async with async_session() as session:
        # Incoming: CASH_IN + transfers received from others
        incoming = await session.execute(
            select(func.coalesce(func.sum(WalletTransaction.amount), 0)).where(
                or_(
                    # Cash in from reports
                    (WalletTransaction.sender_telegram_id == telegram_id) &
                    (WalletTransaction.transaction_type == WalletTransactionType.CASH_IN),
                    # Transfers received from other employees
                    (WalletTransaction.receiver_telegram_id == telegram_id) &
                    (WalletTransaction.transaction_type == WalletTransactionType.TRANSFER_TO_EMPLOYEE),
                )
            )
        )
        total_in = Decimal(str(incoming.scalar()))

        # Outgoing: transfers sent to employees, to Shavkat, to bank
        outgoing = await session.execute(
            select(func.coalesce(func.sum(WalletTransaction.amount), 0)).where(
                WalletTransaction.sender_telegram_id == telegram_id,
                WalletTransaction.transaction_type.in_([
                    WalletTransactionType.TRANSFER_TO_EMPLOYEE,
                    WalletTransactionType.TRANSFER_TO_SHAVKAT,
                    WalletTransactionType.CASH_TO_BANK,
                ]),
            )
        )
        total_out = Decimal(str(outgoing.scalar()))

    return total_in - total_out


async def _notify_admin(bot: Bot, text: str):
    """Send notification to admin."""
    if settings.admin_user_id:
        try:
            await bot.send_message(settings.admin_user_id, text)
        except Exception as e:
            logger.error(f"Failed to notify admin: {e}")


# ────────────────────────────────────────────────────────────────────────
# ENTRY POINT — Show balance + actions
# ────────────────────────────────────────────────────────────────────────


@router.callback_query(F.data == "action:wallet")
async def on_wallet(callback: types.CallbackQuery, state: FSMContext):
    """Show wallet balance and action buttons."""
    async with async_session() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == callback.from_user.id)
        )
        user = result.scalar_one_or_none()

    if not user:
        await callback.answer("Пользователь не найден")
        return

    lang = user.language.value.lower()
    balance = await get_wallet_balance(callback.from_user.id)

    text = (
        f"💰 <b>Кошелёк</b>\n\n"
        f"Баланс: <b>{format_amount(balance)} UZS</b>"
    )

    buttons = [
        [InlineKeyboardButton(text="💼 Инкассация", callback_data="wlt:to_employee")],
        [InlineKeyboardButton(text="🏦 Сдать в банк", callback_data="wlt:to_bank")],
        [InlineKeyboardButton(
            text=f"◀️ {get_text('btn_back', lang)}",
            callback_data="action:back_menu",
        )],
    ]

    await state.set_state(WalletStates.viewing)
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await callback.answer()


# ────────────────────────────────────────────────────────────────────────
# TRANSFER TO EMPLOYEE — choose recipient
# ────────────────────────────────────────────────────────────────────────


@router.callback_query(F.data == "wlt:to_employee", WalletStates.viewing)
async def on_transfer_employee(callback: types.CallbackQuery, state: FSMContext):
    """Show admin users (Акбар, Шавкат) to transfer cash to."""
    async with async_session() as session:
        result = await session.execute(
            select(User).where(
                User.is_active == True,
                User.role == UserRole.ADMIN,
                User.telegram_id != callback.from_user.id,
            ).order_by(User.full_name)
        )
        admins = result.scalars().all()

    if not admins:
        await callback.answer("Нет доступных получателей", show_alert=True)
        return

    buttons = []
    for u in admins:
        buttons.append([InlineKeyboardButton(
            text=u.full_name,
            callback_data=f"wlt_emp:{u.telegram_id}",
        )])
    buttons.append([InlineKeyboardButton(text="❌ Отмена", callback_data="wlt:cancel")])

    await state.update_data(
        transfer_type=WalletTransactionType.TRANSFER_TO_EMPLOYEE.value,
        sender_telegram_id=callback.from_user.id,
    )
    await state.set_state(WalletStates.choosing_recipient)
    await callback.message.edit_text(
        "💼 Выберите получателя инкассации:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("wlt_emp:"), WalletStates.choosing_recipient)
async def on_employee_selected(callback: types.CallbackQuery, state: FSMContext):
    """Employee selected — ask for amount."""
    receiver_tid = int(callback.data.split(":")[1])

    # Get receiver name
    async with async_session() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == receiver_tid)
        )
        receiver = result.scalar_one_or_none()

    receiver_name = receiver.full_name if receiver else "?"
    await state.update_data(
        receiver_telegram_id=receiver_tid,
        receiver_name=receiver_name,
    )

    balance = await get_wallet_balance(callback.from_user.id)
    await state.set_state(WalletStates.entering_amount)
    await callback.message.edit_text(
        f"👤 Получатель: <b>{receiver_name}</b>\n"
        f"💰 Ваш баланс: {format_amount(balance)} UZS\n\n"
        f"Введите сумму перевода:"
    )
    await callback.answer()


# ────────────────────────────────────────────────────────────────────────
# CASH TO BANK — direct amount entry
# ────────────────────────────────────────────────────────────────────────


@router.callback_query(F.data == "wlt:to_bank", WalletStates.viewing)
async def on_cash_to_bank(callback: types.CallbackQuery, state: FSMContext):
    """Cash to bank — ask amount."""
    balance = await get_wallet_balance(callback.from_user.id)
    await state.update_data(
        transfer_type=WalletTransactionType.CASH_TO_BANK.value,
        sender_telegram_id=callback.from_user.id,
        receiver_telegram_id=None,
        receiver_name="Банк",
    )
    await state.set_state(WalletStates.entering_amount)
    await callback.message.edit_text(
        f"🏦 Сдача в банк\n"
        f"💰 Ваш баланс: {format_amount(balance)} UZS\n\n"
        f"Введите сумму:"
    )
    await callback.answer()


# ────────────────────────────────────────────────────────────────────────
# AMOUNT ENTRY
# ────────────────────────────────────────────────────────────────────────


@router.message(WalletStates.entering_amount)
async def on_amount_entered(message: types.Message, state: FSMContext):
    """Parse transfer amount."""
    raw = message.text.strip().replace(" ", "").replace(",", "").replace(".", "")
    try:
        amount = Decimal(raw)
        if amount <= 0:
            raise ValueError
    except (ValueError, Exception):
        await message.answer("❌ Введите корректную сумму (только цифры)")
        return

    data = await state.get_data()
    sender_tid = data["sender_telegram_id"]
    balance = await get_wallet_balance(sender_tid)

    if amount > balance:
        await message.answer(
            f"❌ Недостаточно средств.\n"
            f"Баланс: {format_amount(balance)} UZS\n"
            f"Запрос: {format_amount(amount)} UZS"
        )
        return

    await state.update_data(amount=str(amount))

    # Ask for optional note
    buttons = [
        [InlineKeyboardButton(text="⏩ Пропустить", callback_data="wlt_note:skip")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="wlt:cancel")],
    ]
    await state.set_state(WalletStates.entering_note)
    await message.answer(
        "📝 Добавьте комментарий (или пропустите):",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
    )


# ────────────────────────────────────────────────────────────────────────
# NOTE (optional)
# ────────────────────────────────────────────────────────────────────────


@router.callback_query(F.data == "wlt_note:skip", WalletStates.entering_note)
async def on_note_skip(callback: types.CallbackQuery, state: FSMContext):
    """Note skipped."""
    await state.update_data(note="")
    await _show_confirmation(callback.message, state, edit=True)
    await callback.answer()


@router.message(WalletStates.entering_note)
async def on_note_entered(message: types.Message, state: FSMContext):
    """Note entered."""
    await state.update_data(note=message.text.strip())
    await _show_confirmation(message, state, edit=False)


async def _show_confirmation(message: types.Message, state: FSMContext, edit: bool = False):
    """Show transfer confirmation."""
    data = await state.get_data()
    tx_type = WalletTransactionType(data["transfer_type"])
    tx_label = WALLET_TRANSACTION_TYPE_LABELS.get(tx_type, tx_type.value)
    amount = Decimal(data["amount"])
    receiver_name = data.get("receiver_name", "—")
    note = data.get("note", "")

    summary = (
        f"📝 <b>Подтверждение</b>\n\n"
        f"Операция: {tx_label}\n"
        f"Получатель: {receiver_name}\n"
        f"Сумма: <b>{format_amount(amount)} UZS</b>\n"
    )
    if note:
        summary += f"Комментарий: {note}\n"
    summary += "\nВсё верно?"

    buttons = [
        [
            InlineKeyboardButton(text="✅ Подтвердить", callback_data="wlt:confirm"),
            InlineKeyboardButton(text="❌ Отмена", callback_data="wlt:cancel"),
        ]
    ]

    await state.set_state(WalletStates.confirming)
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    if edit:
        await message.edit_text(summary, reply_markup=kb)
    else:
        await message.answer(summary, reply_markup=kb)


# ────────────────────────────────────────────────────────────────────────
# CONFIRM & SAVE
# ────────────────────────────────────────────────────────────────────────


@router.callback_query(F.data == "wlt:confirm", WalletStates.confirming)
async def on_confirm_transfer(callback: types.CallbackQuery, state: FSMContext):
    """Save wallet transaction and notify admin."""
    data = await state.get_data()
    tx_type = WalletTransactionType(data["transfer_type"])
    amount = Decimal(data["amount"])

    # Double-check balance
    balance = await get_wallet_balance(data["sender_telegram_id"])
    if amount > balance:
        await callback.answer("❌ Недостаточно средств!", show_alert=True)
        return

    async with async_session() as session:
        tx = WalletTransaction(
            sender_telegram_id=data["sender_telegram_id"],
            receiver_telegram_id=data.get("receiver_telegram_id"),
            amount=amount,
            transaction_type=tx_type,
            note=data.get("note") or None,
        )
        session.add(tx)
        await session.commit()

    await state.clear()

    # Get sender name for notification
    async with async_session() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == data["sender_telegram_id"])
        )
        sender = result.scalar_one_or_none()

    sender_name = sender.full_name if sender else "?"
    tx_label = WALLET_TRANSACTION_TYPE_LABELS.get(tx_type, tx_type.value)
    receiver_name = data.get("receiver_name", "—")
    note_text = f"\nКомментарий: {data['note']}" if data.get("note") else ""

    # Notify admin
    admin_text = (
        f"💰 <b>Операция кошелька</b>\n\n"
        f"Отправитель: {sender_name}\n"
        f"Операция: {tx_label}\n"
        f"Получатель: {receiver_name}\n"
        f"Сумма: {format_amount(amount)} UZS{note_text}"
    )
    await _notify_admin(callback.bot, admin_text)

    # Return to main menu
    if sender:
        lang = sender.language.value.lower()
        section = sender.active_section.value.lower()
        section_name = get_text(f"section_{section}", lang)
        await callback.message.edit_text(
            f"✅ {tx_label}: {format_amount(amount)} UZS\n\n"
            f"{get_text('main_menu', lang, section=section_name)}",
            reply_markup=main_menu_keyboard(lang, current_section=section),
        )
    await callback.answer()


# ────────────────────────────────────────────────────────────────────────
# CANCEL
# ────────────────────────────────────────────────────────────────────────


@router.callback_query(F.data == "wlt:cancel")
async def on_cancel_wallet(callback: types.CallbackQuery, state: FSMContext):
    """Cancel wallet operation — back to main menu."""
    await state.clear()

    async with async_session() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == callback.from_user.id)
        )
        user = result.scalar_one_or_none()

    if user:
        lang = user.language.value.lower()
        section = user.active_section.value.lower()
        section_name = get_text(f"section_{section}", lang)
        await callback.message.edit_text(
            get_text("main_menu", lang, section=section_name),
            reply_markup=main_menu_keyboard(lang, current_section=section),
        )
    await callback.answer()
