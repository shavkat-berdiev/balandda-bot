"""SPA bot notifications (@balandda_spa_bot).

Sends Telegram messages via raw HTTPS (no aiogram Bot instance needed), so it
works identically from the API container (instant appointment events) and the
bot container (daily digest). Fully disabled while SPA_BOT_TOKEN is empty.

Recipients:
- the appointment's master (spa_masters.telegram_id, if registered)
- the SPA admin (settings.spa_admin_telegram_id)
- all active OWNER users
"""

import logging
from datetime import datetime, timedelta, timezone

import aiohttp
from sqlalchemy import select

from bot.config import settings
from db.models import SpaAppointment, SpaMaster, User, UserRole

logger = logging.getLogger(__name__)

TASHKENT = timezone(timedelta(hours=5))

EVENT_HEADERS = {
    "created": "🆕 <b>Новая запись SPA</b>",
    "updated": "✏️ <b>Запись SPA изменена</b>",
    "cancelled": "❌ <b>Запись SPA отменена</b>",
    "done": "✅ <b>Услуга выполнена</b>",
    "no_show": "🚫 <b>Клиент не пришёл</b>",
}


def _fmt(amount: float) -> str:
    return f"{amount:,.0f}".replace(",", " ")


def commission_for(svc, master) -> float:
    """Fixed UZS commission for this service+master (by master type)."""
    if master and getattr(master, "master_type", "internal") == "external":
        return float(getattr(svc, "commission_external", 0) or 0)
    return float(getattr(svc, "commission_internal", 0) or 0)


async def send_message(chat_id: int, text: str) -> bool:
    """Send one message via the SPA bot. Never raises."""
    if not settings.spa_bot_token or not chat_id:
        return False
    url = f"https://api.telegram.org/bot{settings.spa_bot_token}/sendMessage"
    try:
        async with aiohttp.ClientSession() as http:
            async with http.post(
                url,
                json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"},
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    logger.warning(f"SPA bot send to {chat_id} failed {resp.status}: {body[:200]}")
                    return False
        return True
    except Exception as e:
        logger.warning(f"SPA bot send to {chat_id} failed: {e}")
        return False


async def _owner_ids(session) -> list[int]:
    rows = (
        await session.execute(
            select(User.telegram_id).where(User.role == UserRole.OWNER, User.is_active == True)  # noqa: E712
        )
    ).scalars().all()
    return list(rows)


def _appt_lines(a: SpaAppointment, with_client: bool = True) -> list[str]:
    start = a.start_at.astimezone(TASHKENT)
    end = a.end_at.astimezone(TASHKENT)
    lines = [
        f"📅 {start.strftime('%d.%m.%Y')} · {start.strftime('%H:%M')}–{end.strftime('%H:%M')}",
        f"💆 {a.service.name_ru if a.service else '—'}",
        f"👤 Мастер: {a.master.name if a.master else '—'}",
    ]
    if a.location:
        lines.append(f"🚪 Кабинет: {a.location.name_ru}")
    if with_client and (a.customer_name or a.customer_phone):
        client = a.customer_name or ""
        if a.customer_phone:
            client = f"{client} ({a.customer_phone})" if client else a.customer_phone
        lines.append(f"🧑 Клиент: {client}")
    lines.append(f"💰 Цена: {_fmt(float(a.price or 0))} UZS")
    if a.note:
        lines.append(f"📝 {a.note}")
    return lines


async def notify_appointment_event(session, appt: SpaAppointment, event: str) -> None:
    """Notify master + SPA admin + owners about an appointment event.

    Must be called with appt loaded incl. service/master/location relations.
    Never raises — a notification failure must not break the API request.
    """
    if not settings.spa_bot_token:
        return
    try:
        header = EVENT_HEADERS.get(event, EVENT_HEADERS["updated"])
        body = "\n".join(_appt_lines(appt))
        commission = commission_for(appt.service, appt.master) if appt.service else 0.0

        # Master — personal message (their commission on completion)
        master_tid = appt.master.telegram_id if appt.master else None
        if master_tid:
            m_lines = [header, "", body]
            if event == "done" and commission:
                m_lines.append(f"\n💵 Ваша комиссия: <b>{_fmt(commission)} UZS</b>")
            elif event in ("created", "updated") and commission:
                m_lines.append(f"\n💵 Комиссия за услугу: {_fmt(commission)} UZS")
            await send_message(master_tid, "\n".join(m_lines))

        # SPA admin + owners — full picture incl. commission
        a_lines = [header, "", body]
        if commission:
            a_lines.append(
                f"\n💵 Комиссия мастера ({'внешний' if appt.master and appt.master.master_type == 'external' else 'внутренний'}): "
                f"{_fmt(commission)} UZS"
            )
        admin_text = "\n".join(a_lines)

        sent: set[int] = {master_tid} if master_tid else set()
        for tid in [settings.spa_admin_telegram_id, *await _owner_ids(session)]:
            if tid and tid not in sent:
                sent.add(tid)
                await send_message(tid, admin_text)
    except Exception as e:
        logger.error(f"SPA notification ({event}) failed: {e}", exc_info=True)


# ── Daily digest (called from bot/scheduler.py) ───────────────────


async def send_daily_digest() -> None:
    """Morning digest: each master gets their day; admin + owners get the full day."""
    if not settings.spa_bot_token:
        return
    from sqlalchemy.orm import selectinload
    from db.database import async_session

    now = datetime.now(TASHKENT)
    day_start = datetime(now.year, now.month, now.day, tzinfo=TASHKENT)
    day_end = day_start + timedelta(days=1)

    async with async_session() as session:
        appts = (
            await session.execute(
                select(SpaAppointment)
                .options(
                    selectinload(SpaAppointment.service),
                    selectinload(SpaAppointment.master),
                    selectinload(SpaAppointment.location),
                )
                .where(
                    SpaAppointment.start_at >= day_start,
                    SpaAppointment.start_at < day_end,
                    SpaAppointment.status.in_(["planned", "done"]),
                )
                .order_by(SpaAppointment.start_at)
            )
        ).scalars().all()
        masters = (
            await session.execute(
                select(SpaMaster).where(SpaMaster.is_active == True)  # noqa: E712
            )
        ).scalars().all()
        owner_ids = await _owner_ids(session)

    date_str = now.strftime("%d.%m.%Y")

    def short(a: SpaAppointment, with_master: bool) -> str:
        t = a.start_at.astimezone(TASHKENT).strftime("%H:%M")
        parts = [f"• {t} — {a.service.name_ru if a.service else '—'}"]
        if with_master:
            parts.append(f"({a.master.name if a.master else '—'})")
        if a.location:
            parts.append(f"· {a.location.name_ru}")
        if a.customer_name:
            parts.append(f"· {a.customer_name}")
        return " ".join(parts)

    # Per-master digests: today's schedule + earnings (yesterday / 7 days / 30 days)
    from services import spa_commissions as sc

    async with async_session() as session2:
        earnings: dict[int, tuple[float, float, float, float]] = {}
        y_start, y_end = sc.day_bounds((now - timedelta(days=1)).date())
        w_start, _ = sc.day_bounds((now - timedelta(days=6)).date())
        m_start, _ = sc.day_bounds((now - timedelta(days=29)).date())
        for m in masters:
            if not m.telegram_id:
                continue
            earnings[m.id] = (
                await sc.earned_in_period(session2, y_start, y_end, m.id),
                await sc.earned_in_period(session2, w_start, day_end, m.id),
                await sc.earned_in_period(session2, m_start, day_end, m.id),
                await sc.master_balance(session2, m.id),
            )

    for m in masters:
        if not m.telegram_id:
            continue
        mine = [a for a in appts if a.master_id == m.id]
        yday, week, month, balance = earnings.get(m.id, (0, 0, 0, 0))
        if not mine and not month and not balance:
            continue  # nothing to say
        lines = [f"📋 <b>Ваше расписание на {date_str}</b>", ""]
        if mine:
            lines += [short(a, with_master=False) for a in mine]
            total_comm = sum(commission_for(a.service, m) for a in mine if a.service)
            if total_comm:
                lines.append(f"\n💵 Комиссия за день (план): {_fmt(total_comm)} UZS")
        else:
            lines.append("Записей на сегодня нет.")
        lines += [
            "",
            "💰 <b>Ваш заработок:</b>",
            f"• Вчера: {_fmt(yday)} UZS",
            f"• За 7 дней: {_fmt(week)} UZS",
            f"• За 30 дней: {_fmt(month)} UZS",
            f"• Не выплачено: <b>{_fmt(balance)} UZS</b>",
        ]
        await send_message(m.telegram_id, "\n".join(lines))

    # Admin + owners — full day (always, so silence ≠ broken bot)
    if appts:
        lines = [f"📋 <b>SPA расписание на {date_str}</b> — {len(appts)} запис.", ""]
        lines += [short(a, with_master=True) for a in appts]
    else:
        lines = [f"📋 <b>SPA расписание на {date_str}</b>", "", "Записей нет."]
    text = "\n".join(lines)
    sent: set[int] = set()
    for tid in [settings.spa_admin_telegram_id, *owner_ids]:
        if tid and tid not in sent:
            sent.add(tid)
            await send_message(tid, text)
