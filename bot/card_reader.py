"""Read-only Telethon reader for CardXabar (UZCARD) transaction messages.

Runs inside the bot process on the same asyncio loop. Logs in with a
StringSession of the owner's personal Telegram account (created once with
scripts/telethon_login.py) and ONLY reads the CardXabar chat — it never sends
messages and never touches other chats.

Fully disabled unless TELETHON_API_ID / TELETHON_API_HASH / TELETHON_SESSION
are set in the environment. On startup it catches up on messages missed while
the bot was down (by message id), then listens for new ones.
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import func, select

from bot.card_parser import parse_cardxabar_message
from bot.config import settings
from db.database import async_session
from db.models import CardTransaction

logger = logging.getLogger(__name__)

CATCHUP_LIMIT = 300  # max history messages to scan on startup
WATCHDOG_INTERVAL = 60   # seconds between Telegram connection checks
POLL_EVERY = 5           # history catch-up every N watchdog ticks (~5 min safety net)
CATCHUP_POST_HOURS = 12  # missed IN transfers newer than this are still posted (marked delayed)
DELAYED_AFTER_MIN = 5    # a caught-up transfer older than this is labelled 'delayed'

_store_lock = asyncio.Lock()  # live handler and poller must not race on the same message

_BUSINESS_LABELS = {"BALANDDA": "Balandda", "XUSH": "XUSH"}


def _fmt_amount(amount: float) -> str:
    return f"{amount:,.0f}".replace(",", " ")


async def _notify_incoming(bot, tx: CardTransaction, delayed: bool = False) -> None:
    """Real-time post of an incoming transfer into the business's bound topic.

    Deliberately NO owner-DM fallback: an unbound category means real-time
    posts are off for that card (the 21:15 daily reconciliation still runs).
    """
    from zoneinfo import ZoneInfo

    from bot.notifications import CAT_CARD_BALANDDA, CAT_CARD_XUSH, send_via_route

    category = {
        "BALANDDA": CAT_CARD_BALANDDA,
        "XUSH": CAT_CARD_XUSH,
    }.get(tx.business or "")
    if category is None:
        return

    label = _BUSINESS_LABELS.get(tx.business, tx.business)
    t = tx.tx_time.astimezone(ZoneInfo(settings.timezone)).strftime("%H:%M")
    src = (tx.merchant or "?").split(",")[0]
    text = (
        f"💳 <b>Поступление на карту {label} (*{tx.card_last4})</b>\n\n"
        f"➕ <b>{_fmt_amount(float(tx.amount))} UZS</b>\n"
        f"📍 {src}\n"
        f"🕓 {t}\n\n"
        f"Проверьте: есть ли этот перевод в отчёте / предоплате."
    )
    if delayed:
        text += "\n\n⏱ <i>Отправлено с задержкой (был сбой связи с Telegram)</i>"
    if not await send_via_route(bot, category, text):
        logger.info(
            f"Real-time card post skipped ({tx.business}): category {category} not bound to a topic"
        )


def is_configured() -> bool:
    return bool(
        settings.telethon_api_id
        and settings.telethon_api_hash
        and settings.telethon_session
    )


async def _store_message(msg_id: int, text: str) -> CardTransaction | None:
    async with _store_lock:
        return await _store_message_unlocked(msg_id, text)


async def _store_message_unlocked(msg_id: int, text: str) -> CardTransaction | None:
    """Parse and store one CardXabar message. Returns the row if new+parsed."""
    parsed = parse_cardxabar_message(text)
    if parsed is None:
        return None

    async with async_session() as session:
        exists = await session.execute(
            select(CardTransaction.id).where(CardTransaction.tg_message_id == msg_id)
        )
        if exists.scalar_one_or_none() is not None:
            return None  # already stored (dedupe)

        tx = CardTransaction(
            tg_message_id=msg_id,
            card_last4=parsed.card_last4,
            business=settings.card_business_map.get(parsed.card_last4),
            direction=parsed.direction,
            tx_type=parsed.tx_type,
            amount=parsed.amount,
            merchant=parsed.merchant,
            tx_time=parsed.tx_time,
            balance_after=parsed.balance_after,
            raw_text=parsed.raw_text,
        )
        session.add(tx)
        await session.commit()
        logger.info(
            f"Card tx stored: {parsed.direction} {parsed.amount:.0f} UZS "
            f"*{parsed.card_last4} ({tx.business or 'unknown card'}) — {parsed.merchant}"
        )
        return tx


async def _last_stored_message_id() -> int:
    async with async_session() as session:
        result = await session.execute(select(func.max(CardTransaction.tg_message_id)))
        return result.scalar_one_or_none() or 0


async def _resolve_chat(client):
    """Find the CardXabar dialog by @username, numeric id, or exact title.

    A fresh StringSession has an empty entity cache, so get_entity(<id>) fails
    until the dialog has been seen once — scanning dialogs both finds the chat
    and populates the cache.
    """
    ref = settings.cardxabar_chat.strip()
    if ref.startswith("@"):
        return await client.get_entity(ref)
    if ref.lstrip("-").isdigit():
        target_id = int(ref)
        try:
            return await client.get_entity(target_id)
        except ValueError:
            async for dialog in client.iter_dialogs():
                if dialog.id == target_id or getattr(dialog.entity, "id", None) == abs(target_id):
                    return dialog.entity
            return None
    async for dialog in client.iter_dialogs():
        if (dialog.name or "").strip().lower() == ref.lower():
            return dialog.entity
    return None


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=ZoneInfo(settings.timezone))


async def _post_incoming(bot, tx: CardTransaction | None, delayed: bool = False) -> None:
    if tx is None or bot is None or tx.direction != "IN" or not tx.business:
        return
    try:
        await _notify_incoming(bot, tx, delayed=delayed)
    except Exception as e:
        logger.error(f"Card reader: real-time post failed: {e}", exc_info=True)


async def _catch_up(client, chat, bot) -> int:
    """Store CardXabar messages newer than the last stored one.

    Incoming business transfers younger than CATCHUP_POST_HOURS are still
    posted to their topic (labelled delayed if late); older ones are stored
    silently so a first start or a long outage doesn't flood the group.
    Dedup by tg_message_id guarantees nothing is posted twice.
    """
    last_id = await _last_stored_message_id()
    new: list[CardTransaction] = []
    async for msg in client.iter_messages(chat, min_id=last_id, limit=CATCHUP_LIMIT):
        if msg.text:
            tx = await _store_message(msg.id, msg.text)
            if tx is not None:
                new.append(tx)
    now = datetime.now(timezone.utc)
    for tx in sorted(new, key=lambda t: t.tg_message_id):
        age = now - _aware(tx.tx_time)
        if age <= timedelta(hours=CATCHUP_POST_HOURS):
            await _post_incoming(bot, tx, delayed=age > timedelta(minutes=DELAYED_AFTER_MIN))
    if new:
        logger.info(f"Card reader: caught up {len(new)} missed transaction(s)")
    return len(new)


async def _watchdog(client, chat, bot) -> None:
    """Keep the userbot alive.

    Telethon gives up after a few failed reconnects (2026-10-16: a 6-minute
    network blip at 06:30 left the reader dead all morning). This loop
    reconnects whenever the client is down and periodically re-reads history
    so nothing is missed even if live updates silently stall.
    """
    tick = 0
    while True:
        await asyncio.sleep(WATCHDOG_INTERVAL)
        tick += 1
        try:
            if not client.is_connected():
                logger.warning("Card reader: Telegram connection lost — reconnecting")
                await client.connect()
                logger.info("Card reader: reconnected to Telegram")
                await _catch_up(client, chat, bot)
                tick = 0
            elif tick >= POLL_EVERY:
                tick = 0
                await _catch_up(client, chat, bot)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.warning(f"Card reader: watchdog error ({e.__class__.__name__}: {e}) — retrying")


async def start_card_reader(bot=None):
    """Connect and start listening. Returns the client, or None if disabled/failed.

    bot: aiogram Bot for real-time incoming-transfer posts to group topics
    (catch-up messages never trigger posts — only live events do).
    """
    if not is_configured():
        logger.info("Card reader disabled (TELETHON_* env vars not set)")
        return None

    try:
        from telethon import TelegramClient, events
        from telethon.sessions import StringSession
    except ImportError:
        logger.error("Card reader: telethon is not installed — add it to dependencies")
        return None

    client = TelegramClient(
        StringSession(settings.telethon_session),
        settings.telethon_api_id,
        settings.telethon_api_hash,
    )

    try:
        await client.connect()
        if not await client.is_user_authorized():
            logger.error(
                "Card reader: session not authorized — re-create it with "
                "scripts/telethon_login.py and update TELETHON_SESSION"
            )
            await client.disconnect()
            return None

        chat = await _resolve_chat(client)
        if chat is None:
            logger.error(
                f"Card reader: chat '{settings.cardxabar_chat}' not found among dialogs"
            )
            await client.disconnect()
            return None

        # Catch up on messages missed while we were down (recent IN ones get posted)
        await _catch_up(client, chat, bot)

        async def _handle_live(event):
            tx = await _store_message(event.message.id, event.message.text)
            # Real-time group post for NEW incoming transfers on business cards
            await _post_incoming(bot, tx)

        @client.on(events.NewMessage(chats=chat))
        async def _on_new_message(event):
            try:
                if event.message.text:
                    await _handle_live(event)
            except Exception as e:
                logger.error(f"Card reader: failed to process message: {e}", exc_info=True)

        @client.on(events.MessageEdited(chats=chat))
        async def _on_edited_message(event):
            # CardXabar occasionally edits messages; try to store if we missed it
            try:
                if event.message.text:
                    await _handle_live(event)
            except Exception as e:
                logger.error(f"Card reader: failed to process edit: {e}", exc_info=True)

        client._card_watchdog = asyncio.create_task(_watchdog(client, chat, bot))
        logger.info("Card reader started — listening to CardXabar (watchdog on)")
        return client

    except Exception as e:
        logger.error(f"Card reader failed to start: {e}", exc_info=True)
        try:
            await client.disconnect()
        except Exception:
            pass
        return None
