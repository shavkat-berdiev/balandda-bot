"""Shared notification module — routes activity notifications either into the
Reporting group's forum topics (per-category, see NotificationRoute) or, when a
category is not bound to a topic, to OWNER users' private chats (legacy
behavior, also the fallback if a group send fails).

All public notify_* functions are fire-and-forget: they schedule the actual
send as a background task so the calling handler never blocks on network I/O.
"""

import asyncio
import logging
import time

from aiogram import Bot
from sqlalchemy import select

from db.database import async_session
from db.enums import UserRole
from db.models import NotificationRoute, User

logger = logging.getLogger(__name__)


# ────────────────────────────────────────────────────────────────────────
# Notification categories (values stored in notification_routes.category)
# ────────────────────────────────────────────────────────────────────────

CAT_INKASSATSIYA = "INKASSATSIYA"   # wallet transfers: created / accepted / declined
CAT_OPERATIONS = "OPERATIONS"       # income / expense entries, purchases (закуп)
CAT_REPORTS = "REPORTS"             # submitted reports + daily 21:00 summary
CAT_BOOKINGS = "BOOKINGS"           # prepayments / booking money-in
CAT_SYSTEM = "SYSTEM"               # system events, errors, misc
CAT_CARD_BALANDDA = "CARD_BALANDDA" # card-transfer reconciliation, Balandda card
CAT_CARD_XUSH = "CARD_XUSH"         # card-transfer reconciliation, XUSH card

CATEGORY_LABELS: dict[str, str] = {
    CAT_INKASSATSIYA: "💰 Инкассация",
    CAT_OPERATIONS: "📈 Операции (доходы/расходы)",
    CAT_REPORTS: "📊 Отчёты и сводки",
    CAT_BOOKINGS: "🏨 Брони и предоплаты",
    CAT_SYSTEM: "⚙️ Система",
    CAT_CARD_BALANDDA: "💳 Карта Balandda (сверка)",
    CAT_CARD_XUSH: "💳 Карта XUSH (сверка)",
}


# ────────────────────────────────────────────────────────────────────────
# Route lookup (60s cache so every notification doesn't hit the DB)
# ────────────────────────────────────────────────────────────────────────

_ROUTE_CACHE_TTL = 60.0
_route_cache: dict[str, tuple[int, int | None]] = {}
_route_cache_at: float = 0.0


async def _load_routes() -> dict[str, tuple[int, int | None]]:
    async with async_session() as session:
        result = await session.execute(select(NotificationRoute))
        return {
            r.category: (r.chat_id, r.thread_id)
            for r in result.scalars().all()
        }


async def _get_route(category: str | None) -> tuple[int, int | None] | None:
    """Return (chat_id, thread_id) for a category, or None if unbound."""
    global _route_cache, _route_cache_at
    if category is None:
        return None
    now = time.monotonic()
    if now - _route_cache_at > _ROUTE_CACHE_TTL:
        try:
            _route_cache = await _load_routes()
            _route_cache_at = now
        except Exception as e:
            logger.error(f"Failed to load notification routes: {e}")
            return None
    return _route_cache.get(category)


def invalidate_route_cache() -> None:
    """Force the next notification to re-read routes from the DB."""
    global _route_cache_at
    _route_cache_at = 0.0


# ────────────────────────────────────────────────────────────────────────
# Send primitives
# ────────────────────────────────────────────────────────────────────────

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


async def _send_to_owners(bot: Bot, text: str, exclude_tid: int | None = None):
    """Send a notification message to all OWNER users' private chats."""
    owner_ids = await _get_owner_ids()
    for tid in owner_ids:
        if tid == exclude_tid:
            continue
        try:
            await bot.send_message(tid, text, parse_mode="HTML")
        except Exception as e:
            logger.error(f"Failed to notify owner {tid}: {e}")


async def send_via_route(bot: Bot, category: str | None, text: str) -> bool:
    """Try to post into the bound group topic. Returns True on success."""
    route = await _get_route(category)
    if not route:
        return False
    chat_id, thread_id = route
    try:
        await bot.send_message(
            chat_id, text, message_thread_id=thread_id, parse_mode="HTML"
        )
        return True
    except Exception as e:
        logger.error(
            f"Failed to send {category} notification to group {chat_id} "
            f"(topic {thread_id}): {e} — falling back to owner DMs"
        )
        return False


async def _dispatch(bot: Bot, text: str, category: str | None,
                    exclude_tid: int | None = None):
    """Route to the group topic if bound; otherwise (or on failure) owner DMs."""
    if await send_via_route(bot, category, text):
        return
    await _send_to_owners(bot, text, exclude_tid=exclude_tid)


def notify_owners(bot: Bot, text: str, exclude_tid: int | None = None,
                  category: str | None = None):
    """Fire-and-forget: schedule notification as a background task."""
    asyncio.create_task(_dispatch(bot, text, category, exclude_tid=exclude_tid))


def format_amount(amount) -> str:
    """Format number as readable currency string."""
    return f"{int(float(amount)):,}".replace(",", " ")


# ────────────────────────────────────────────────────────────────────────
# Typed notifications
# ────────────────────────────────────────────────────────────────────────

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
    notify_owners(bot, text, category=CAT_REPORTS)


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
    notify_owners(bot, text, category=CAT_BOOKINGS)


async def notify_wallet_transfer(bot: Bot, sender_name: str, tx_label: str,
                                  receiver_name: str, amount: float,
                                  note: str | None = None,
                                  exclude_tid: int | None = None):
    """Notify owners when a wallet transfer is made.

    exclude_tid: skip this telegram_id from owner notification
    (used when the receiver is an OWNER — they already got the accept/decline message).
    Only applies to the DM fallback; the group topic always gets the message.
    """
    note_text = f"\n📝 {note}" if note else ""
    text = (
        f"💼 <b>Операция кошелька</b>\n\n"
        f"👤 {sender_name}\n"
        f"🔄 {tx_label}\n"
        f"➡️ {receiver_name}\n"
        f"💰 {format_amount(amount)} UZS{note_text}"
    )
    notify_owners(bot, text, exclude_tid=exclude_tid, category=CAT_INKASSATSIYA)


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
    notify_owners(bot, text, category=CAT_OPERATIONS)


async def notify_entry_corrected(bot: Bot, user_name: str, kind: str, label: str,
                                  old_amount: float, new_amount: float | None,
                                  wallet_delta: float, business_unit: str,
                                  wallet_owner_name: str | None = None):
    """Notify owners when somebody corrects or deletes an entry.

    Corrections are self-service for staff (own entries, draft report only), so
    the owner always sees old → new and exactly how the wallet moved. Anything
    that changes money must be visible — see services/entry_corrections.py.
    """
    bu_label = "Курорт" if business_unit == "RESORT" else "Ресторан"
    icon = "📈" if kind == "income" else "📉"
    head = "удалён" if new_amount is None else "исправлен"
    money = (
        f"💰 {format_amount(old_amount)} → <s>удалено</s>"
        if new_amount is None
        else f"💰 {format_amount(old_amount)} → <b>{format_amount(new_amount)}</b> UZS"
    )
    text = (
        f"✏️ <b>{icon} {'Доход' if kind == 'income' else 'Расход'} {head}</b>\n\n"
        f"👤 {user_name}\n"
        f"🏢 {bu_label}\n"
        f"📝 {label}\n"
        f"{money}"
    )
    if wallet_delta:
        sign = "+" if wallet_delta > 0 else "−"
        who = f" ({wallet_owner_name})" if wallet_owner_name else ""
        text += f"\n👛 Кошелёк{who}: {sign}{format_amount(abs(wallet_delta))} UZS"
    notify_owners(bot, text, category=CAT_OPERATIONS)


async def notify_transfer_reversed(bot: Bot, actor_name: str, sender_name: str,
                                    receiver_name: str, amount: float, reason: str | None = None):
    """Notify owners when an accepted transfer was unwound (wrong recipient)."""
    text = (
        f"↩️ <b>Перевод возвращён</b>\n\n"
        f"👤 Вернул: {actor_name}\n"
        f"➡️ Было: {sender_name} → {receiver_name}\n"
        f"💰 {format_amount(amount)} UZS\n"
        f"👛 Деньги вернулись отправителю"
    )
    if reason:
        text += f"\n📝 {reason}"
    notify_owners(bot, text, category=CAT_OPERATIONS)


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
    notify_owners(bot, text, category=CAT_OPERATIONS)
