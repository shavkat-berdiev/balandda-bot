"""Wallet handler — cash balance tracking and transfers with receiver acceptance.

Flow:
1. User taps "💰 Кошелёк" → show balance + action buttons
2. Actions: Transfer to employee, Cash to bank
3. Transfer flow: select recipient → enter amount → optional note → confirm
4. On confirm: create PENDING transaction, deduct from sender, send accept/decline to receiver
5. Receiver accepts → COMPLETED; Receiver declines → CANCELLED, money returns to sender
6. Auto CASH_IN happens in new_report.py when cash income is saved (always COMPLETED)
"""

import logging
from decimal import Decimal

from datetime import date, timedelta

from aiogram import Bot, F, Router, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import select, func, case, or_, and_

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


class WalletStates(StatesGroup):
    viewing = State()
    choosing_recipient = State()
    entering_amount = State()
    entering_note = State()
    confirming = State()
    entering_cash_in_amount = State()


def format_amount(amount: float | Decimal) -> str:
    """Format amount with dot separators (e.g., 3.200.000)."""
    if isinstance(amount, Decimal):
        amount = float(amount)
    return f"{amount:,.0f}".replace(",", ".")


async def get_wallet_balance(telegram_id: int) -> Decimal:
    """Calculate current wallet balance for a user.

    Balance = SUM(CASH_IN) + SUM(received COMPLETED transfers)
            - SUM(sent transfers that are PENDING or COMPLETED)
            - SUM(COMPLETED final destinations)

    PENDING outgoing deducts from sender (money is frozen).
    Only COMPLETED incoming adds to receiver.
    """
    async with async_session() as session:
        # Incoming: CASH_IN (always COMPLETED) + COMPLETED transfers received
        incoming = await session.execute(
            select(func.coalesce(func.sum(WalletTransaction.amount), 0)).where(
                or_(
                    # Cash in from reports (always COMPLETED)
                    and_(
                        WalletTransaction.sender_telegram_id == telegram_id,
                        WalletTransaction.transaction_type == WalletTransactionType.CASH_IN,
                        WalletTransaction.status == WalletTransactionStatus.COMPLETED,
                    ),
                    # Transfers received from other employees — only COMPLETED
                    and_(
                        WalletTransaction.receiver_telegram_id == telegram_id,
                        WalletTransaction.transaction_type == WalletTransactionType.TRANSFER_TO_EMPLOYEE,
                        WalletTransaction.status == WalletTransactionStatus.COMPLETED,
                    ),
                )
            )
        )
        total_in = Decimal(str(incoming.scalar()))

        # Outgoing: PENDING + COMPLETED transfers sent (money is frozen/gone)
        outgoing = await session.execute(
            select(func.coalesce(func.sum(WalletTransaction.amount), 0)).where(
                WalletTransaction.sender_telegram_id == telegram_id,
                WalletTransaction.transaction_type.in_([
                    WalletTransactionType.TRANSFER_TO_EMPLOYEE,
                    WalletTransactionType.TRANSFER_TO_SHAVKAT,
                    WalletTransactionType.CASH_TO_BANK,
                    WalletTransactionType.PURCHASE,
                    WalletTransactionType.SALARY,
                    WalletTransactionType.EXPENSE,
                ]),
                WalletTransaction.status.in_([
                    WalletTransactionStatus.PENDING,
                    WalletTransactionStatus.COMPLETED,
                ]),
            )
        )
        total_out = Decimal(str(outgoing.scalar()))

        # Owner balance corrections (signed delta)
        adj = await session.execute(
            select(func.coalesce(func.sum(WalletTransaction.amount), 0)).where(
                WalletTransaction.sender_telegram_id == telegram_id,
                WalletTransaction.transaction_type == WalletTransactionType.ADJUSTMENT,
                WalletTransaction.status == WalletTransactionStatus.COMPLETED,
            )
        )
        total_adj = Decimal(str(adj.scalar()))

    return total_in - total_out + total_adj


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

    # Check for pending incoming transfers
    async with async_session() as session:
        pending_result = await session.execute(
            select(func.count()).where(
                WalletTransaction.receiver_telegram_id == callback.from_user.id,
                WalletTransaction.status == WalletTransactionStatus.PENDING,
            )
        )
        pending_count = pending_result.scalar()

    text = (
        f"💰 <b>Кошелёк</b>\n\n"
        f"Баланс: <b>{format_amount(balance)} UZS</b>"
    )
    if pending_count:
        text += f"\n\n⏳ У вас <b>{pending_count}</b> входящих переводов на подтверждение"

    buttons = [
        [InlineKeyboardButton(text="💼 Инкассация", callback_data="wlt:to_employee")],
        [InlineKeyboardButton(text="👑 Передать владельцу", callback_data="wlt:to_owner")],
        [InlineKeyboardButton(text="🏦 Сдать в банк", callback_data="wlt:to_bank")],
        [InlineKeyboardButton(text="📊 Мой отчёт", callback_data="wlt:my_report")],
    ]
    # XUSH section: manual cash-in button
    if user.active_section.value == "XUSH":
        buttons.insert(0, [InlineKeyboardButton(
            text="💵 Приход наличных",
            callback_data="wlt:xush_cash_in",
        )])
    if pending_count:
        buttons.insert(0, [InlineKeyboardButton(
            text=f"📥 Входящие ({pending_count})",
            callback_data="wlt:pending_inbox",
        )])
    buttons.append([InlineKeyboardButton(
        text=f"◀️ {get_text('btn_back', lang)}",
        callback_data="action:back_menu",
    )])

    await state.set_state(WalletStates.viewing)
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await callback.answer()


@router.message(Command("balance"))
async def cmd_balance(message: types.Message, state: FSMContext):
    """Quick on-demand balance check."""
    bal = await get_wallet_balance(message.from_user.id)
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="💰 Открыть кошелёк", callback_data="action:wallet"),
    ]])
    await message.answer(f"💰 Ваш баланс: <b>{format_amount(bal)} UZS</b>", reply_markup=kb)


# ────────────────────────────────────────────────────────────────────────
# PENDING INBOX — show incoming transfers
# ────────────────────────────────────────────────────────────────────────


@router.callback_query(F.data == "wlt:pending_inbox", WalletStates.viewing)
async def on_pending_inbox(callback: types.CallbackQuery, state: FSMContext):
    """Show list of pending incoming transfers."""
    async with async_session() as session:
        result = await session.execute(
            select(WalletTransaction).where(
                WalletTransaction.receiver_telegram_id == callback.from_user.id,
                WalletTransaction.status == WalletTransactionStatus.PENDING,
            ).order_by(WalletTransaction.created_at.desc())
        )
        pending_txs = result.scalars().all()

        # Get sender names
        sender_ids = {tx.sender_telegram_id for tx in pending_txs}
        if sender_ids:
            users_result = await session.execute(
                select(User).where(User.telegram_id.in_(sender_ids))
            )
            user_map = {u.telegram_id: u.full_name for u in users_result.scalars().all()}
        else:
            user_map = {}

    if not pending_txs:
        await callback.answer("Нет входящих переводов", show_alert=True)
        return

    text = "📥 <b>Входящие переводы</b>\n\n"
    buttons = []
    for tx in pending_txs:
        sender_name = user_map.get(tx.sender_telegram_id, "?")
        tx_label = WALLET_TRANSACTION_TYPE_LABELS.get(tx.transaction_type, tx.transaction_type.value)
        note_text = f" — {tx.note}" if tx.note else ""
        text += f"• {sender_name}: <b>{format_amount(tx.amount)} UZS</b> ({tx_label}){note_text}\n"
        buttons.append([
            InlineKeyboardButton(
                text=f"✅ {sender_name} — {format_amount(tx.amount)}",
                callback_data=f"wlt_accept:{tx.id}",
            ),
            InlineKeyboardButton(
                text="❌",
                callback_data=f"wlt_decline:{tx.id}",
            ),
        ])

    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="action:wallet")])

    await callback.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
    )
    await callback.answer()


# ────────────────────────────────────────────────────────────────────────
# ACCEPT / DECLINE pending transfers
# ────────────────────────────────────────────────────────────────────────


@router.callback_query(F.data.startswith("wlt_accept:"))
async def on_accept_transfer(callback: types.CallbackQuery, state: FSMContext):
    """Receiver accepts a pending transfer."""
    tx_id = int(callback.data.split(":")[1])

    async with async_session() as session:
        result = await session.execute(
            select(WalletTransaction).where(WalletTransaction.id == tx_id)
        )
        tx = result.scalar_one_or_none()

        if not tx or tx.status != WalletTransactionStatus.PENDING:
            await callback.answer("Этот перевод уже обработан", show_alert=True)
            return

        if tx.receiver_telegram_id != callback.from_user.id:
            await callback.answer("Это не ваш перевод", show_alert=True)
            return

        tx.status = WalletTransactionStatus.COMPLETED
        await session.commit()

        # Get names for notification
        sender_result = await session.execute(
            select(User).where(User.telegram_id == tx.sender_telegram_id)
        )
        sender = sender_result.scalar_one_or_none()
        receiver_result = await session.execute(
            select(User).where(User.telegram_id == tx.receiver_telegram_id)
        )
        receiver = receiver_result.scalar_one_or_none()

    sender_name = sender.full_name if sender else "?"
    receiver_name = receiver.full_name if receiver else "?"
    tx_label = WALLET_TRANSACTION_TYPE_LABELS.get(tx.transaction_type, tx.transaction_type.value)

    # Notify sender
    try:
        await callback.bot.send_message(
            tx.sender_telegram_id,
            f"✅ <b>Перевод принят</b>\n\n"
            f"Получатель {receiver_name} принял вашу инкассацию\n"
            f"Сумма: {format_amount(tx.amount)} UZS",
            parse_mode="HTML",
        )
    except Exception as e:
        logger.error(f"Failed to notify sender {tx.sender_telegram_id}: {e}")

    # Notify owners
    await notify_wallet_transfer(
        callback.bot, sender_name, f"{tx_label} ✅",
        receiver_name, float(tx.amount), tx.note,
    )

    await callback.answer("✅ Перевод принят!")

    # Refresh inbox
    await on_wallet(callback, state)


@router.callback_query(F.data.startswith("wlt_decline:"))
async def on_decline_transfer(callback: types.CallbackQuery, state: FSMContext):
    """Receiver declines a pending transfer — money returns to sender."""
    tx_id = int(callback.data.split(":")[1])

    async with async_session() as session:
        result = await session.execute(
            select(WalletTransaction).where(WalletTransaction.id == tx_id)
        )
        tx = result.scalar_one_or_none()

        if not tx or tx.status != WalletTransactionStatus.PENDING:
            await callback.answer("Этот перевод уже обработан", show_alert=True)
            return

        if tx.receiver_telegram_id != callback.from_user.id:
            await callback.answer("Это не ваш перевод", show_alert=True)
            return

        tx.status = WalletTransactionStatus.CANCELLED
        await session.commit()

        # Get names
        sender_result = await session.execute(
            select(User).where(User.telegram_id == tx.sender_telegram_id)
        )
        sender = sender_result.scalar_one_or_none()
        receiver_result = await session.execute(
            select(User).where(User.telegram_id == tx.receiver_telegram_id)
        )
        receiver = receiver_result.scalar_one_or_none()

    sender_name = sender.full_name if sender else "?"
    receiver_name = receiver.full_name if receiver else "?"

    # Notify sender that transfer was declined
    try:
        await callback.bot.send_message(
            tx.sender_telegram_id,
            f"❌ <b>Перевод отклонён</b>\n\n"
            f"Получатель {receiver_name} отклонил инкассацию\n"
            f"Сумма: {format_amount(tx.amount)} UZS\n\n"
            f"Средства возвращены в ваш кошелёк.",
            parse_mode="HTML",
        )
    except Exception as e:
        logger.error(f"Failed to notify sender {tx.sender_telegram_id}: {e}")

    # Notify owners
    tx_label = WALLET_TRANSACTION_TYPE_LABELS.get(tx.transaction_type, tx.transaction_type.value)
    await notify_wallet_transfer(
        callback.bot, sender_name, f"{tx_label} ❌ отклонён",
        receiver_name, float(tx.amount), tx.note,
    )

    await callback.answer("❌ Перевод отклонён")

    # Refresh inbox
    await on_wallet(callback, state)


# ────────────────────────────────────────────────────────────────────────
# TRANSFER TO EMPLOYEE — choose recipient
# ────────────────────────────────────────────────────────────────────────


@router.callback_query(F.data == "wlt:to_employee", WalletStates.viewing)
async def on_transfer_employee(callback: types.CallbackQuery, state: FSMContext):
    """Show all active employees to transfer cash to."""
    async with async_session() as session:
        result = await session.execute(
            select(User).where(
                User.is_active == True,
                User.telegram_id != callback.from_user.id,
            ).order_by(User.full_name)
        )
        recipients = result.scalars().all()

    if not recipients:
        await callback.answer("Нет доступных получателей", show_alert=True)
        return

    buttons = []
    for u in recipients:
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
# TRANSFER TO OWNER (final destination, owner must accept)
# ────────────────────────────────────────────────────────────────────────


@router.callback_query(F.data == "wlt:to_owner", WalletStates.viewing)
async def on_transfer_owner(callback: types.CallbackQuery, state: FSMContext):
    """Send the final amount to the owner — a final destination he must accept."""
    async with async_session() as session:
        result = await session.execute(
            select(User).where(
                User.is_active == True,
                User.role == UserRole.OWNER,
                User.telegram_id != callback.from_user.id,
            ).order_by(User.full_name)
        )
        owners = result.scalars().all()

    if not owners:
        await callback.answer("Владелец не найден", show_alert=True)
        return

    owner = owners[0]
    await state.update_data(
        transfer_type=WalletTransactionType.TRANSFER_TO_SHAVKAT.value,
        sender_telegram_id=callback.from_user.id,
        receiver_telegram_id=owner.telegram_id,
        receiver_name=owner.full_name,
    )
    balance = await get_wallet_balance(callback.from_user.id)
    await state.set_state(WalletStates.entering_amount)
    await callback.message.edit_text(
        f"👑 Передать владельцу: <b>{owner.full_name}</b>\n"
        f"💰 Ваш баланс: {format_amount(balance)} UZS\n\n"
        f"Введите сумму (владелец подтвердит получение):"
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

    if tx_type == WalletTransactionType.TRANSFER_TO_EMPLOYEE:
        summary += "\n⏳ Получатель должен будет подтвердить получение."
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
    """Save wallet transaction.

    - TRANSFER_TO_EMPLOYEE → PENDING (awaiting receiver acceptance)
    - CASH_TO_BANK / TRANSFER_TO_SHAVKAT → COMPLETED immediately
    """
    data = await state.get_data()
    tx_type = WalletTransactionType(data["transfer_type"])
    amount = Decimal(data["amount"])

    # Determine status
    needs_acceptance = tx_type in (
        WalletTransactionType.TRANSFER_TO_EMPLOYEE,
        WalletTransactionType.TRANSFER_TO_SHAVKAT,
    )
    status = WalletTransactionStatus.PENDING if needs_acceptance else WalletTransactionStatus.COMPLETED

    async with async_session() as session:
        tx = WalletTransaction(
            sender_telegram_id=data["sender_telegram_id"],
            receiver_telegram_id=data.get("receiver_telegram_id"),
            amount=amount,
            transaction_type=tx_type,
            status=status,
            note=data.get("note") or None,
        )
        session.add(tx)
        await session.commit()
        tx_id = tx.id

    await state.clear()
    await callback.answer()

    # Get sender name
    async with async_session() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == data["sender_telegram_id"])
        )
        sender = result.scalar_one_or_none()

    sender_name = sender.full_name if sender else "?"
    tx_label = WALLET_TRANSACTION_TYPE_LABELS.get(tx_type, tx_type.value)
    receiver_name = data.get("receiver_name", "—")

    if needs_acceptance:
        # Send accept/decline to receiver
        receiver_tid = data.get("receiver_telegram_id")
        if receiver_tid:
            note_text = f"\n📝 {data['note']}" if data.get("note") else ""
            try:
                await callback.bot.send_message(
                    receiver_tid,
                    f"📥 <b>Входящий перевод</b>\n\n"
                    f"👤 Отправитель: {sender_name}\n"
                    f"💰 Сумма: <b>{format_amount(amount)} UZS</b>\n"
                    f"📋 {tx_label}{note_text}\n\n"
                    f"Подтвердите получение:",
                    parse_mode="HTML",
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                        [
                            InlineKeyboardButton(
                                text="✅ Принять",
                                callback_data=f"wlt_accept:{tx_id}",
                            ),
                            InlineKeyboardButton(
                                text="❌ Отклонить",
                                callback_data=f"wlt_decline:{tx_id}",
                            ),
                        ]
                    ]),
                )
            except Exception as e:
                logger.error(f"Failed to send acceptance request to {receiver_tid}: {e}")

        # Notify owners about pending transfer (exclude receiver — they got accept/decline buttons)
        await notify_wallet_transfer(
            callback.bot, sender_name, f"{tx_label} ⏳",
            receiver_name, float(amount), data.get("note"),
            exclude_tid=data.get("receiver_telegram_id"),
        )

        # Show sender confirmation
        if sender:
            lang = sender.language.value.lower()
            section = sender.active_section.value.lower()
            section_name = get_text(f"section_{section}", lang)
            await callback.message.edit_text(
                f"⏳ {tx_label}: {format_amount(amount)} UZS\n"
                f"Ожидает подтверждения от {receiver_name}\n\n"
                f"{get_text('main_menu', lang, section=section_name)}",
                reply_markup=main_menu_keyboard(lang, current_section=section),
            )
    else:
        # Completed immediately (CASH_TO_BANK)
        await notify_wallet_transfer(
            callback.bot, sender_name, tx_label,
            receiver_name, float(amount), data.get("note"),
        )

        if sender:
            lang = sender.language.value.lower()
            section = sender.active_section.value.lower()
            section_name = get_text(f"section_{section}", lang)
            await callback.message.edit_text(
                f"✅ {tx_label}: {format_amount(amount)} UZS\n\n"
                f"{get_text('main_menu', lang, section=section_name)}",
                reply_markup=main_menu_keyboard(lang, current_section=section),
            )


# ────────────────────────────────────────────────────────────────────────
# MY REPORT — employee transaction summary
# ────────────────────────────────────────────────────────────────────────


@router.callback_query(F.data == "wlt:my_report", WalletStates.viewing)
async def on_my_report(callback: types.CallbackQuery, state: FSMContext):
    """Show period selection for personal report."""
    buttons = [
        [InlineKeyboardButton(text="📅 Сегодня", callback_data="wlt_rpt:today")],
        [InlineKeyboardButton(text="📅 Эта неделя", callback_data="wlt_rpt:week")],
        [InlineKeyboardButton(text="📅 Этот месяц", callback_data="wlt_rpt:month")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="action:wallet")],
    ]
    await callback.message.edit_text(
        "📊 <b>Мой отчёт</b>\n\nВыберите период:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("wlt_rpt:"), WalletStates.viewing)
async def on_my_report_period(callback: types.CallbackQuery, state: FSMContext):
    """Show personal transaction report for selected period."""
    period = callback.data.split(":")[1]
    today = date.today()

    if period == "today":
        start = today
        period_label = "Сегодня"
    elif period == "week":
        start = today - timedelta(days=today.weekday())  # Monday
        period_label = "Эта неделя"
    else:  # month
        start = today.replace(day=1)
        period_label = "Этот месяц"

    tid = callback.from_user.id
    balance = await get_wallet_balance(tid)

    async with async_session() as session:
        # Get all wallet transactions for this user in the period
        result = await session.execute(
            select(WalletTransaction).where(
                or_(
                    WalletTransaction.sender_telegram_id == tid,
                    WalletTransaction.receiver_telegram_id == tid,
                ),
                WalletTransaction.created_at >= start,
                WalletTransaction.status.in_([
                    WalletTransactionStatus.COMPLETED,
                    WalletTransactionStatus.PENDING,
                ]),
            ).order_by(WalletTransaction.created_at.desc())
        )
        txs = result.scalars().all()

        # Get user names
        user_ids = set()
        for tx in txs:
            user_ids.add(tx.sender_telegram_id)
            if tx.receiver_telegram_id:
                user_ids.add(tx.receiver_telegram_id)
        user_map = {}
        if user_ids:
            users_result = await session.execute(
                select(User).where(User.telegram_id.in_(user_ids))
            )
            user_map = {u.telegram_id: u.full_name for u in users_result.scalars().all()}

    # Build summary
    total_in = Decimal(0)
    total_out = Decimal(0)
    lines = []

    for tx in txs:
        tx_label = WALLET_TRANSACTION_TYPE_LABELS.get(tx.transaction_type, tx.transaction_type.value)
        status_icon = "⏳" if tx.status == WalletTransactionStatus.PENDING else ""
        tx_date = tx.created_at.strftime("%d.%m") if tx.created_at else ""

        if tx.transaction_type == WalletTransactionType.CASH_IN and tx.sender_telegram_id == tid:
            total_in += tx.amount
            lines.append(f"  📈 {tx_date} +{format_amount(tx.amount)} {tx_label}")
        elif tx.receiver_telegram_id == tid and tx.sender_telegram_id != tid:
            if tx.status == WalletTransactionStatus.COMPLETED:
                total_in += tx.amount
            sender = user_map.get(tx.sender_telegram_id, "?")
            lines.append(f"  📥 {tx_date} +{format_amount(tx.amount)} от {sender} {status_icon}")
        elif tx.sender_telegram_id == tid and tx.transaction_type != WalletTransactionType.CASH_IN:
            total_out += tx.amount
            receiver = user_map.get(tx.receiver_telegram_id, "") if tx.receiver_telegram_id else ""
            dest = f"→ {receiver}" if receiver else ""
            lines.append(f"  📤 {tx_date} -{format_amount(tx.amount)} {tx_label} {dest} {status_icon}")

    text = (
        f"📊 <b>Мой отчёт — {period_label}</b>\n"
        f"📅 {start.strftime('%d.%m.%Y')} — {today.strftime('%d.%m.%Y')}\n\n"
        f"💰 Баланс: <b>{format_amount(balance)} UZS</b>\n"
        f"📈 Приход: +{format_amount(total_in)} UZS\n"
        f"📤 Расход: -{format_amount(total_out)} UZS\n"
    )

    if lines:
        text += f"\n<b>Операции ({len(lines)}):</b>\n" + "\n".join(lines[:20])
        if len(lines) > 20:
            text += f"\n  ... и ещё {len(lines) - 20}"
    else:
        text += "\nНет операций за этот период"

    buttons = [
        [
            InlineKeyboardButton(text="📅 Сегодня", callback_data="wlt_rpt:today"),
            InlineKeyboardButton(text="📅 Неделя", callback_data="wlt_rpt:week"),
            InlineKeyboardButton(text="📅 Месяц", callback_data="wlt_rpt:month"),
        ],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="action:wallet")],
    ]

    await callback.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
    )
    await callback.answer()


# ────────────────────────────────────────────────────────────────────────
# XUSH MANUAL CASH-IN — user enters cash amount manually
# ────────────────────────────────────────────────────────────────────────


@router.callback_query(F.data == "wlt:xush_cash_in", WalletStates.viewing)
async def on_xush_cash_in(callback: types.CallbackQuery, state: FSMContext):
    """Prompt user to enter cash amount for manual cash-in."""
    balance = await get_wallet_balance(callback.from_user.id)

    await state.set_state(WalletStates.entering_cash_in_amount)
    await callback.message.edit_text(
        f"💵 <b>Приход наличных (XUSH)</b>\n\n"
        f"💰 Текущий баланс: <b>{format_amount(balance)} UZS</b>\n\n"
        f"Введите сумму прихода:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀️ Назад", callback_data="action:wallet")],
        ]),
    )
    await callback.answer()


@router.message(WalletStates.entering_cash_in_amount)
async def on_xush_cash_in_amount(message: types.Message, state: FSMContext):
    """Parse cash-in amount, create CASH_IN transaction."""
    text = message.text.strip().replace(" ", "").replace(".", "").replace(",", "")
    if not text.isdigit() or int(text) <= 0:
        await message.answer("Введите корректную сумму (только цифры).")
        return

    amount = Decimal(text)

    async with async_session() as session:
        session.add(WalletTransaction(
            sender_telegram_id=message.from_user.id,
            amount=amount,
            transaction_type=WalletTransactionType.CASH_IN,
            status=WalletTransactionStatus.COMPLETED,
            note="Приход наличных",
            business_unit="XUSH",
        ))
        await session.commit()

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

    await state.clear()
    await message.answer(
        f"✅ Приход наличных: +{format_amount(amount)} UZS\n"
        f"💰 Баланс кассы: <b>{format_amount(balance)} UZS</b>\n\n"
        f"{get_text('main_menu', lang, section=section_name)}",
        reply_markup=main_menu_keyboard(lang, current_section=section, role=user.role.value if user else ""),
    )


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
