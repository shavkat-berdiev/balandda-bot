"""@balandda_spa_bot — dedicated SPA bot.

Roles (by Telegram ID):
- SPA admin (settings.spa_admin_telegram_id) and active OWNER users:
  menu with today's records, per-master commissions, payouts (deducts from the
  payer's analytics cash wallet as a SALARY transaction) and guest payment
  acceptance (same ledger flow as accommodation payments).
- Registered master (spa_masters.telegram_id): their records + their earnings.
- Anyone else: shown their Telegram ID to send to Shavkat for registration.

No-op while SPA_BOT_TOKEN is empty.
"""

import asyncio
import logging
from datetime import datetime, timedelta

from aiogram import Bot, Dispatcher, F, Router, types
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from bot.config import settings
from db.database import async_session
from db.enums import PAYMENT_METHOD_LABELS
from db.models import (
    IncomeEntry,
    PaymentMethod,
    SpaAppointment,
    SpaMaster,
    User,
    UserRole,
)
from services import spa_commissions as sc
from services.spa_payments import record_spa_payment
from services.spa_notify import send_message as spa_send

logger = logging.getLogger(__name__)

spa_router = Router()

TASHKENT = sc.TASHKENT

PAY_METHODS = [
    PaymentMethod.CASH, PaymentMethod.CARD_TRANSFER, PaymentMethod.TERMINAL_UZCARD,
    PaymentMethod.TERMINAL_VISA, PaymentMethod.PAYME, PaymentMethod.WIRE_TRANSFER,
]


def _fmt(n: float) -> str:
    return f"{n:,.0f}".replace(",", " ")


async def _is_admin(tid: int) -> bool:
    if settings.spa_admin_telegram_id and tid == settings.spa_admin_telegram_id:
        return True
    async with async_session() as session:
        role = (
            await session.execute(
                select(User.role).where(User.telegram_id == tid, User.is_active == True)  # noqa: E712
            )
        ).scalar_one_or_none()
    return role == UserRole.OWNER


async def _get_master(tid: int) -> SpaMaster | None:
    async with async_session() as session:
        return (
            await session.execute(select(SpaMaster).where(SpaMaster.telegram_id == tid))
        ).scalar_one_or_none()


def _admin_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 Записи сегодня", callback_data="recs")],
        [InlineKeyboardButton(text="💰 Комиссии мастеров", callback_data="comm")],
        [InlineKeyboardButton(text="💳 Принять оплату", callback_data="payl")],
    ])


def _master_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 Мои записи сегодня", callback_data="myrecs")],
        [InlineKeyboardButton(text="💰 Мои комиссии", callback_data="mycomm")],
    ])


def _back(to: str = "menu") -> list[InlineKeyboardButton]:
    return [InlineKeyboardButton(text="⬅️ Меню", callback_data=to)]


async def _today_appts(session, master_id: int | None = None):
    now = datetime.now(TASHKENT)
    start, end = sc.day_bounds(now.date())
    stmt = (
        select(SpaAppointment)
        .options(
            selectinload(SpaAppointment.service),
            selectinload(SpaAppointment.master),
            selectinload(SpaAppointment.location),
        )
        .where(
            SpaAppointment.start_at >= start,
            SpaAppointment.start_at < end,
            SpaAppointment.status != "cancelled",
        )
        .order_by(SpaAppointment.start_at)
    )
    if master_id:
        stmt = stmt.where(SpaAppointment.master_id == master_id)
    return (await session.execute(stmt)).scalars().all()


def _appt_line(a: SpaAppointment, with_master: bool = True) -> str:
    t = a.start_at.astimezone(TASHKENT).strftime("%H:%M")
    status = {"done": " ✅", "no_show": " 🚫"}.get(a.status, "")
    parts = [f"• {t} — {a.service.name_ru if a.service else '—'}"]
    if with_master:
        parts.append(f"({a.master.name if a.master else '—'})")
    if a.customer_name:
        parts.append(f"· {a.customer_name}")
    parts.append(f"· {_fmt(float(a.price or 0))}")
    return " ".join(parts) + status


# ── Entry: /start and any text ────────────────────────────────────


@spa_router.message()
async def any_message(message: types.Message):
    tid = message.from_user.id if message.from_user else None
    if not tid:
        return
    if await _is_admin(tid):
        await message.answer("🛠 <b>SPA Balandda — меню администратора</b>", reply_markup=_admin_menu())
        return
    master = await _get_master(tid)
    if master:
        role = "внешний мастер" if master.master_type == "external" else "мастер"
        await message.answer(
            f"👋 <b>{master.name}</b> ({role})", reply_markup=_master_menu()
        )
    else:
        await message.answer(
            "👋 Это бот SPA Balandda.\n\n"
            f"Ваш Telegram ID: <code>{tid}</code>\n\n"
            "Отправьте этот номер Шавкату — после регистрации сюда будут "
            "приходить ваши записи."
        )


@spa_router.callback_query(F.data == "menu")
async def cb_menu(cb: types.CallbackQuery):
    if await _is_admin(cb.from_user.id):
        await cb.message.edit_text("🛠 <b>SPA Balandda — меню администратора</b>", reply_markup=_admin_menu())
    else:
        master = await _get_master(cb.from_user.id)
        if master:
            await cb.message.edit_text(f"👋 <b>{master.name}</b>", reply_markup=_master_menu())
    await cb.answer()


# ── Admin: today's records ────────────────────────────────────────


@spa_router.callback_query(F.data == "recs")
async def cb_recs(cb: types.CallbackQuery):
    if not await _is_admin(cb.from_user.id):
        return await cb.answer("Нет доступа")
    async with async_session() as session:
        appts = await _today_appts(session)
    date_str = datetime.now(TASHKENT).strftime("%d.%m.%Y")
    if appts:
        text = f"📋 <b>Записи на {date_str}</b> — {len(appts)}\n\n" + "\n".join(_appt_line(a) for a in appts)
    else:
        text = f"📋 <b>Записи на {date_str}</b>\n\nЗаписей нет."
    await cb.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[_back()]))
    await cb.answer()


# ── Admin: commissions + payouts ──────────────────────────────────


@spa_router.callback_query(F.data == "comm")
async def cb_comm(cb: types.CallbackQuery):
    if not await _is_admin(cb.from_user.id):
        return await cb.answer("Нет доступа")
    async with async_session() as session:
        masters = (
            await session.execute(
                select(SpaMaster).where(SpaMaster.is_active == True)  # noqa: E712
                .order_by(SpaMaster.sort_order, SpaMaster.name)
            )
        ).scalars().all()
        rows = []
        for m in masters:
            bal = await sc.master_balance(session, m.id)
            rows.append([InlineKeyboardButton(
                text=f"{m.name} — к выплате {_fmt(bal)}",
                callback_data=f"comm:{m.id}",
            )])
    rows.append(_back())
    await cb.message.edit_text(
        "💰 <b>Комиссии мастеров</b>\n\nВыберите мастера:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )
    await cb.answer()


async def _master_comm_text(session, m: SpaMaster) -> str:
    now = datetime.now(TASHKENT)
    t_start, t_end = sc.day_bounds(now.date())
    y_start, y_end = sc.day_bounds((now - timedelta(days=1)).date())
    w_start, _ = sc.day_bounds((now - timedelta(days=6)).date())
    m_start, _ = sc.day_bounds((now - timedelta(days=29)).date())
    today = await sc.earned_in_period(session, t_start, t_end, m.id)
    yday = await sc.earned_in_period(session, y_start, y_end, m.id)
    week = await sc.earned_in_period(session, w_start, t_end, m.id)
    month = await sc.earned_in_period(session, m_start, t_end, m.id)
    balance = await sc.master_balance(session, m.id)
    kind = "внешний" if (m.master_type or "internal") == "external" else "внутренний"
    recent = await sc.done_appointments(session, m_start, t_end, m.id)
    lines = [
        f"👤 <b>{m.name}</b> ({kind})",
        "",
        f"• Сегодня: {_fmt(today)} UZS",
        f"• Вчера: {_fmt(yday)} UZS",
        f"• За 7 дней: {_fmt(week)} UZS",
        f"• За 30 дней: {_fmt(month)} UZS",
        "",
        f"💵 <b>К выплате: {_fmt(balance)} UZS</b>",
    ]
    if recent:
        lines += ["", "Последние выполненные:"]
        for a in recent[-5:]:
            d = a.start_at.astimezone(TASHKENT).strftime("%d.%m %H:%M")
            lines.append(f"• {d} — {a.service.name_ru if a.service else '—'} · {_fmt(sc.commission_amount(a.service, a.master))}")
    return "\n".join(lines)


@spa_router.callback_query(F.data.startswith("comm:"))
async def cb_comm_master(cb: types.CallbackQuery):
    if not await _is_admin(cb.from_user.id):
        return await cb.answer("Нет доступа")
    mid = int(cb.data.split(":")[1])
    async with async_session() as session:
        m = await session.get(SpaMaster, mid)
        if not m:
            return await cb.answer("Мастер не найден")
        text = await _master_comm_text(session, m)
        balance = await sc.master_balance(session, mid)
    rows = []
    if balance > 0:
        rows.append([InlineKeyboardButton(
            text=f"💸 Выплатить {_fmt(balance)} UZS", callback_data=f"payout:{mid}")])
    rows.append([InlineKeyboardButton(text="⬅️ К мастерам", callback_data="comm")])
    await cb.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))
    await cb.answer()


@spa_router.callback_query(F.data.startswith("payout:"))
async def cb_payout_confirm(cb: types.CallbackQuery):
    if not await _is_admin(cb.from_user.id):
        return await cb.answer("Нет доступа")
    mid = int(cb.data.split(":")[1])
    async with async_session() as session:
        m = await session.get(SpaMaster, mid)
        balance = await sc.master_balance(session, mid)
    if not m or balance <= 0:
        return await cb.answer("Нечего выплачивать")
    await cb.message.edit_text(
        f"💸 Выплатить <b>{m.name}</b> комиссию <b>{_fmt(balance)} UZS</b>?\n\n"
        f"Сумма спишется с вашего кошелька в analytics.berdiev.uz.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Да, выплатить", callback_data=f"payoutok:{mid}")],
            [InlineKeyboardButton(text="⬅️ Отмена", callback_data=f"comm:{mid}")],
        ]),
    )
    await cb.answer()


@spa_router.callback_query(F.data.startswith("payoutok:"))
async def cb_payout_do(cb: types.CallbackQuery):
    if not await _is_admin(cb.from_user.id):
        return await cb.answer("Нет доступа")
    mid = int(cb.data.split(":")[1])
    async with async_session() as session:
        m = await session.get(SpaMaster, mid)
        balance = await sc.master_balance(session, mid)
        if not m or balance <= 0:
            return await cb.answer("Нечего выплачивать")
        try:
            await sc.create_payout(session, mid, balance, cb.from_user.id)
            await session.commit()
        except ValueError as e:
            await session.rollback()
            return await cb.answer(str(e), show_alert=True)
    if m.telegram_id:
        await spa_send(m.telegram_id, f"💸 Вам выплачена комиссия: <b>{_fmt(balance)} UZS</b>")
    await cb.message.edit_text(
        f"✅ Выплачено: <b>{m.name}</b> — <b>{_fmt(balance)} UZS</b>\n"
        f"Списано с вашего кошелька.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ К мастерам", callback_data="comm")], _back(),
        ]),
    )
    await cb.answer("Выплата записана")


# ── Admin: accept guest payment ───────────────────────────────────


@spa_router.callback_query(F.data == "payl")
async def cb_pay_list(cb: types.CallbackQuery):
    if not await _is_admin(cb.from_user.id):
        return await cb.answer("Нет доступа")
    async with async_session() as session:
        appts = await _today_appts(session)
        paid_map = {
            aid: float(total or 0)
            for aid, total in (
                await session.execute(
                    select(IncomeEntry.spa_appointment_id, func.sum(IncomeEntry.amount))
                    .where(IncomeEntry.spa_appointment_id.in_([a.id for a in appts] or [0]))
                    .group_by(IncomeEntry.spa_appointment_id)
                )
            ).all()
        }
    unpaid = [a for a in appts if float(a.price or 0) - paid_map.get(a.id, 0) > 0]
    if not unpaid:
        await cb.message.edit_text(
            "💳 Сегодня нет записей с неоплаченным остатком.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[_back()]),
        )
        return await cb.answer()
    rows = []
    for a in unpaid:
        remaining = float(a.price or 0) - paid_map.get(a.id, 0)
        t = a.start_at.astimezone(TASHKENT).strftime("%H:%M")
        who = a.customer_name or (a.master.name if a.master else "")
        rows.append([InlineKeyboardButton(
            text=f"{t} {a.service.name_ru if a.service else ''} · {who} — {_fmt(remaining)}",
            callback_data=f"pay:{a.id}",
        )])
    rows.append(_back())
    await cb.message.edit_text(
        "💳 <b>Принять оплату</b>\n\nВыберите запись (показан остаток к оплате):",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )
    await cb.answer()


@spa_router.callback_query(F.data.startswith("pay:"))
async def cb_pay_methods(cb: types.CallbackQuery):
    if not await _is_admin(cb.from_user.id):
        return await cb.answer("Нет доступа")
    aid = int(cb.data.split(":")[1])
    async with async_session() as session:
        a = (
            await session.execute(
                select(SpaAppointment).options(selectinload(SpaAppointment.service))
                .where(SpaAppointment.id == aid)
            )
        ).scalar_one_or_none()
        if not a:
            return await cb.answer("Запись не найдена")
        paid = float((await session.execute(
            select(func.coalesce(func.sum(IncomeEntry.amount), 0))
            .where(IncomeEntry.spa_appointment_id == aid)
        )).scalar() or 0)
    remaining = float(a.price or 0) - paid
    if remaining <= 0:
        return await cb.answer("Уже оплачено")
    rows = [
        [InlineKeyboardButton(
            text=PAYMENT_METHOD_LABELS.get(pm, pm.value),
            callback_data=f"paym:{aid}:{pm.value}",
        )]
        for pm in PAY_METHODS
    ]
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="payl")])
    await cb.message.edit_text(
        f"💳 <b>{a.service.name_ru if a.service else ''}</b>\n"
        f"К оплате: <b>{_fmt(remaining)} UZS</b>\n\nСпособ оплаты:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )
    await cb.answer()


@spa_router.callback_query(F.data.startswith("paym:"))
async def cb_pay_do(cb: types.CallbackQuery):
    if not await _is_admin(cb.from_user.id):
        return await cb.answer("Нет доступа")
    _, aid_s, pm_s = cb.data.split(":", 2)
    aid = int(aid_s)
    try:
        pm = PaymentMethod(pm_s)
    except ValueError:
        return await cb.answer("Неверный способ оплаты")
    async with async_session() as session:
        a = (
            await session.execute(
                select(SpaAppointment).options(selectinload(SpaAppointment.service))
                .where(SpaAppointment.id == aid)
            )
        ).scalar_one_or_none()
        if not a or a.status == "cancelled":
            return await cb.answer("Запись недоступна")
        paid = float((await session.execute(
            select(func.coalesce(func.sum(IncomeEntry.amount), 0))
            .where(IncomeEntry.spa_appointment_id == aid)
        )).scalar() or 0)
        remaining = float(a.price or 0) - paid
        if remaining <= 0:
            return await cb.answer("Уже оплачено")
        await record_spa_payment(session, a, remaining, pm, cb.from_user.id)
        await session.commit()
    await cb.message.edit_text(
        f"✅ Оплата принята: <b>{_fmt(remaining)} UZS</b> "
        f"({PAYMENT_METHOD_LABELS.get(pm, pm.value)})\n"
        f"{a.service.name_ru if a.service else ''} — записано в отчёт (SPA).",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💳 Ещё оплата", callback_data="payl")], _back(),
        ]),
    )
    await cb.answer("Оплата записана")


# ── Master: my records + my commissions ───────────────────────────


@spa_router.callback_query(F.data == "myrecs")
async def cb_my_recs(cb: types.CallbackQuery):
    master = await _get_master(cb.from_user.id)
    if not master:
        return await cb.answer("Вы не зарегистрированы")
    async with async_session() as session:
        appts = await _today_appts(session, master.id)
    date_str = datetime.now(TASHKENT).strftime("%d.%m.%Y")
    if appts:
        text = f"📋 <b>Ваши записи на {date_str}</b>\n\n" + "\n".join(_appt_line(a, with_master=False) for a in appts)
    else:
        text = f"📋 <b>Ваши записи на {date_str}</b>\n\nЗаписей нет."
    await cb.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[_back()]))
    await cb.answer()


@spa_router.callback_query(F.data == "mycomm")
async def cb_my_comm(cb: types.CallbackQuery):
    master = await _get_master(cb.from_user.id)
    if not master:
        return await cb.answer("Вы не зарегистрированы")
    async with async_session() as session:
        text = await _master_comm_text(session, master)
    await cb.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[_back()]))
    await cb.answer()


# ── Startup ───────────────────────────────────────────────────────


def start_spa_bot() -> tuple[Bot, asyncio.Task] | None:
    """Launch SPA bot polling as a background task. Returns None if disabled."""
    if not settings.spa_bot_token:
        logger.info("SPA bot disabled (SPA_BOT_TOKEN empty)")
        return None
    bot = Bot(
        token=settings.spa_bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher()
    dp.include_router(spa_router)
    task = asyncio.create_task(
        dp.start_polling(bot, allowed_updates=["message", "callback_query"], handle_signals=False)
    )
    logger.info("SPA bot polling started")
    return bot, task
