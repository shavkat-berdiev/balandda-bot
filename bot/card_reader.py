"""Read-only Telethon reader for CardXabar (UZCARD) transaction messages.

Runs inside the bot process on the same asyncio loop. Logs in with a
StringSession of the owner's personal Telegram account (created once with
scripts/telethon_login.py) and ONLY reads the CardXabar chat — it never sends
messages and never touches other chats.

Fully disabled unless TELETHON_API_ID / TELETHON_API_HASH / TELETHON_SESSION
are set in the environment. On startup it catches up on messages missed while
the bot was down (by message id), then listens for new ones.
"""

import logging

from sqlalchemy import func, select

from bot.card_parser import parse_cardxabar_message
from bot.config import settings
from db.database import async_session
from db.models import CardTransaction

logger = logging.getLogger(__name__)

CATCHUP_LIMIT = 300  # max history messages to scan on startup

_BUSINESS_LABELS = {"BALANDDA": "Balandda", "XUSH": "XUSH"}


def _fmt_amount(amount: float) -> str:
    return f"{amount:,.0f}".replace(",", " ")


async def _notify_incoming(bot, tx: CardTransaction) -> None:
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

        # Catch up on messages missed while we were down
        last_id = await _last_stored_message_id()
        caught_up = 0
        async for msg in client.iter_messages(chat, min_id=last_id, limit=CATCHUP_LIMIT):
            if msg.text and await _store_message(msg.id, msg.text):
                caught_up += 1
        if caught_up:
            logger.info(f"Card reader: caught up {caught_up} missed transaction(s)")

        async def _handle_live(event):
            tx = await _store_message(event.message.id, event.message.text)
            # Real-time group post for NEW incoming transfers on business cards
            if tx is not None and bot is not None and tx.direction == "IN" and tx.business:
                try:
                    await _notify_incoming(bot, tx)
                except Exception as e:
                    logger.error(f"Card reader: real-time post failed: {e}", exc_info=True)

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

        logger.info("Card reader started — listening to CardXabar")
        return client

    except Exception as e:
        logger.error(f"Card reader failed to start: {e}", exc_info=True)
        try:
            await client.disconnect()
        except Exception:
            pass
        return None
