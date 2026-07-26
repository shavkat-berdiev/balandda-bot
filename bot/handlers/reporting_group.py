"""Reporting group — bind notification categories to forum topics.

Usage (inside the Reporting supergroup with Topics enabled):
  1. Open a topic (e.g. "💰 Инкассация")
  2. Send /bind — the bot shows category buttons
  3. Tap a category — notifications of that category now post into this topic

  /routes — show current bindings
  /unbind — remove all bindings of the current topic

Only OWNER users may manage bindings. This router is included FIRST in
main_router and swallows every other group message, so the private-chat
flows (reports, wallet, etc.) can never be triggered from inside a group.
"""

import logging

from aiogram import F, Router, types
from aiogram.filters import Command
from sqlalchemy import delete, select

from bot.notifications import (
    CATEGORY_LABELS,
    invalidate_route_cache,
)
from db.database import async_session
from db.enums import UserRole
from db.models import NotificationRoute, User

logger = logging.getLogger(__name__)

router = Router(name="reporting_group")

IS_GROUP = F.chat.type.in_({"group", "supergroup"})


async def _is_owner(telegram_id: int) -> bool:
    async with async_session() as session:
        result = await session.execute(
            select(User).where(
                User.telegram_id == telegram_id,
                User.role == UserRole.OWNER,
                User.is_active == True,
            )
        )
        return result.scalar_one_or_none() is not None


def _topic_ref(thread_id: int | None) -> str:
    return f"топик #{thread_id}" if thread_id else "General (основной топик)"


@router.message(IS_GROUP, Command("bind"))
async def cmd_bind(message: types.Message):
    """Show category buttons; the chosen category binds to the current topic."""
    if not await _is_owner(message.from_user.id):
        return

    thread_id = message.message_thread_id  # None in the General topic
    buttons = [
        [types.InlineKeyboardButton(
            text=label,
            callback_data=f"ntopic:set:{cat}",
        )]
        for cat, label in CATEGORY_LABELS.items()
    ]
    buttons.append([types.InlineKeyboardButton(
        text="❌ Отмена", callback_data="ntopic:cancel",
    )])
    await message.reply(
        f"🔗 Привязка уведомлений к этому топику ({_topic_ref(thread_id)}).\n"
        f"Выберите категорию:",
        reply_markup=types.InlineKeyboardMarkup(inline_keyboard=buttons),
    )


@router.message(IS_GROUP, Command("routes"))
async def cmd_routes(message: types.Message):
    """Show all current category → topic bindings."""
    if not await _is_owner(message.from_user.id):
        return

    async with async_session() as session:
        result = await session.execute(select(NotificationRoute))
        routes = {r.category: r for r in result.scalars().all()}

    lines = ["📌 <b>Маршруты уведомлений</b>", ""]
    for cat, label in CATEGORY_LABELS.items():
        r = routes.get(cat)
        if r:
            where = r.topic_name or _topic_ref(r.thread_id)
            lines.append(f"{label} → {where}")
        else:
            lines.append(f"{label} → 📩 личные сообщения владельцам")
    lines.append("")
    lines.append("Привязать: откройте топик и отправьте /bind")
    lines.append("Отвязать текущий топик: /unbind")
    await message.reply("\n".join(lines), parse_mode="HTML")


@router.message(IS_GROUP, Command("unbind"))
async def cmd_unbind(message: types.Message):
    """Remove all category bindings pointing at the current topic."""
    if not await _is_owner(message.from_user.id):
        return

    thread_id = message.message_thread_id
    async with async_session() as session:
        result = await session.execute(
            select(NotificationRoute).where(
                NotificationRoute.chat_id == message.chat.id,
                NotificationRoute.thread_id == thread_id,
            )
        )
        found = result.scalars().all()
        cats = [r.category for r in found]
        if cats:
            await session.execute(
                delete(NotificationRoute).where(
                    NotificationRoute.category.in_(cats)
                )
            )
            await session.commit()

    invalidate_route_cache()
    if cats:
        labels = ", ".join(CATEGORY_LABELS.get(c, c) for c in cats)
        await message.reply(
            f"🔓 Отвязано: {labels}\n"
            f"Эти уведомления снова идут владельцам в личные сообщения."
        )
    else:
        await message.reply("К этому топику ничего не привязано.")


@router.callback_query(F.data.startswith("ntopic:"))
async def on_bind_callback(callback: types.CallbackQuery):
    """Save the chosen category → current topic binding."""
    if not await _is_owner(callback.from_user.id):
        await callback.answer("Только для владельцев", show_alert=True)
        return

    action = callback.data.split(":")[1]
    if action == "cancel":
        try:
            await callback.message.delete()
        except Exception:
            pass
        await callback.answer("Отменено")
        return

    category = callback.data.split(":")[2]
    if category not in CATEGORY_LABELS:
        await callback.answer("Неизвестная категория", show_alert=True)
        return

    chat = callback.message.chat
    thread_id = callback.message.message_thread_id  # None for General

    async with async_session() as session:
        route = await session.get(NotificationRoute, category)
        if route is None:
            route = NotificationRoute(category=category)
            session.add(route)
        route.chat_id = chat.id
        route.thread_id = thread_id
        route.chat_title = chat.title
        route.topic_name = None  # Bot API can't read topic names; keep reference simple
        await session.commit()

    invalidate_route_cache()
    label = CATEGORY_LABELS[category]
    logger.info(
        f"Notification route set: {category} → chat {chat.id}, topic {thread_id} "
        f"(by {callback.from_user.id})"
    )
    try:
        await callback.message.edit_text(
            f"✅ <b>{label}</b> — уведомления теперь приходят в этот топик.",
            parse_mode="HTML",
        )
    except Exception:
        pass
    await callback.answer("Привязано ✅")


# ────────────────────────────────────────────────────────────────────────
# Swallow everything else in groups so private-chat flows can't fire there.
# Must stay the LAST handler in this router.
# ────────────────────────────────────────────────────────────────────────

@router.message(IS_GROUP)
async def ignore_group_messages(message: types.Message):
    """Silently consume non-command group traffic (bot may be a group admin)."""
    return
