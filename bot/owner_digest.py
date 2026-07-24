"""Owner daily digests — 09:00 morning and 21:00 evening summaries.

Sent ONLY to OWNER users (contains wallet balances and full money-in figures).

Morning (09:00):
  • today's check-ins: count, booking value, fully paid vs pending
  • yesterday's check-ins that are still not fully paid
  • money in for YESTERDAY (complete day): report entries by payment method + Billz (XUSH)
  • cash wallet balances per user

Evening (21:00):
  • today's check-ins payment status
  • money in for TODAY so far: report entries by payment method + Billz (XUSH)
  • cash wallet balances per user
"""

import logging
from datetime import date, timedelta

from aiogram import Bot, Router, types
from aiogram.filters import Command, CommandObject
from sqlalchemy import func, or_, select

from bot.billz import get_billz_client
from bot.config import settings
from bot.notifications import _get_owner_ids
from services import iiko
from db.database import async_session
from db.enums import (
    PAYMENT_METHOD_LABELS,
    ReportStatus,
    ReservationStatus,
)
from db.models import (
    IncomeEntry,
    Property,
    Reservation,
    StructuredReport,
    User,
)

logger = logging.getLogger(__name__)

# Arrivals we count as "bookings for the day" (everything that isn't dead or a manual block)
_ACTIVE_STATUSES = [
    ReservationStatus.HOLD,
    ReservationStatus.CONFIRMED,
    ReservationStatus.CHECKED_IN,
    ReservationStatus.CHECKED_OUT,
]


def fmt(amount) -> str:
    """3.200.000-style formatting."""
    return f"{float(amount):,.0f}".replace(",", ".")


# ── Data collectors ─────────────────────────────────────────────────


async def get_checkins(target: date) -> dict:
    """Check-ins for a date with paid/pending split.

    "Paid" is the payment ledger (IncomeEntry linked to the reservation);
    deposit_amount is only a legacy fallback — same rule as the calendar API.
    """
    async with async_session() as session:
        rows = (
            await session.execute(
                select(Reservation, Property.name_ru)
                .join(Property, Reservation.property_id == Property.id)
                .where(
                    Reservation.check_in == target,
                    Reservation.status.in_(_ACTIVE_STATUSES),
                )
                .order_by(Property.sort_order)
            )
        ).all()

        res_ids = [r.Reservation.id for r in rows]
        paid_map: dict[int, float] = {}
        if res_ids:
            paid_rows = (
                await session.execute(
                    select(
                        IncomeEntry.reservation_id,
                        func.coalesce(func.sum(IncomeEntry.amount), 0),
                    )
                    .where(IncomeEntry.reservation_id.in_(res_ids))
                    .group_by(IncomeEntry.reservation_id)
                )
            ).all()
            paid_map = {rid: float(total) for rid, total in paid_rows}

    total_value = 0.0
    fully_paid = 0
    pending = 0
    pending_outstanding = 0.0
    pending_items: list[str] = []

    for row in rows:
        res = row.Reservation
        prop_name = row.name_ru
        total = float(res.total_amount) if res.total_amount is not None else None
        ledger = paid_map.get(res.id, 0.0)
        deposit = float(res.deposit_amount) if res.deposit_amount is not None else 0.0
        paid = ledger if ledger > 0 else deposit

        if total:
            total_value += total

        if total is not None and paid >= total - 0.5:
            fully_paid += 1
        else:
            pending += 1
            outstanding = (total - paid) if total is not None else 0.0
            if outstanding > 0:
                pending_outstanding += outstanding
            guest = res.guest_name or (
                f"@{res.telegram_username}" if res.telegram_username else "гость"
            )
            if total is not None:
                pending_items.append(f"{prop_name} · {guest} · остаток {fmt(outstanding)}")
            else:
                pending_items.append(f"{prop_name} · {guest} · сумма не указана")

    return {
        "count": len(rows),
        "total_value": total_value,
        "fully_paid": fully_paid,
        "pending": pending,
        "pending_outstanding": pending_outstanding,
        "pending_items": pending_items,
    }


async def get_money_in(target: date, business_unit=None) -> dict:
    """Money-in for a date, by payment method — everything confirmed by users:
    entries from submitted reports PLUS calendar payments (linked to a reservation),
    which sit in DRAFT reports until the operator submits the day.
    Optionally filtered to one business unit."""
    conditions = [
        StructuredReport.report_date == target,
        or_(
            StructuredReport.status != ReportStatus.DRAFT,
            IncomeEntry.reservation_id.is_not(None),
        ),
    ]
    if business_unit is not None:
        conditions.append(StructuredReport.business_unit == business_unit)

    async with async_session() as session:
        rows = (
            await session.execute(
                select(
                    IncomeEntry.payment_method,
                    func.coalesce(func.sum(IncomeEntry.amount), 0),
                )
                .join(StructuredReport, IncomeEntry.report_id == StructuredReport.id)
                .where(*conditions)
                .group_by(IncomeEntry.payment_method)
            )
        ).all()

    by_method = []
    total = 0.0
    for pm, amt in sorted(rows, key=lambda r: float(r[1]), reverse=True):
        label = PAYMENT_METHOD_LABELS.get(pm, pm.value if hasattr(pm, "value") else str(pm))
        by_method.append((label, float(amt)))
        total += float(amt)

    return {"by_method": by_method, "total": total}


async def get_billz_summary(target: date) -> dict | None:
    """XUSH sales from Billz POS for a date; None if not configured / unavailable."""
    if not settings.billz_api_key:
        return None
    try:
        client = get_billz_client()
        return await client.get_daily_cash_total(target)
    except Exception as e:
        logger.warning(f"Billz daily total for {target} failed: {e}")
        return {"error": str(e)}


async def get_wallet_balances() -> list[tuple[str, float]]:
    """Cash-on-hand per active user (non-zero only), sorted by balance desc."""
    from bot.handlers.wallet import get_wallet_balance

    async with async_session() as session:
        users = (
            await session.execute(
                select(User).where(User.is_active == True).order_by(User.full_name)
            )
        ).scalars().all()

    balances = []
    for u in users:
        try:
            bal = float(await get_wallet_balance(u.telegram_id))
        except Exception as e:
            logger.error(f"Wallet balance for {u.telegram_id} failed: {e}")
            continue
        if round(bal) != 0:
            balances.append((u.full_name, bal))

    balances.sort(key=lambda x: x[1], reverse=True)
    return balances


# ── Message sections ────────────────────────────────────────────────


def _checkins_block(title: str, c: dict, show_pending_list: bool = True) -> list[str]:
    lines = [f"📅 <b>{title}</b>"]
    if c["count"] == 0:
        lines.append("Заездов нет.")
        return lines
    lines.append(f"Всего: <b>{c['count']}</b> брон. на <b>{fmt(c['total_value'])} UZS</b>")
    lines.append(f"✅ Полностью оплачено: {c['fully_paid']}")
    if c["pending"]:
        lines.append(
            f"⏳ Ожидают оплаты: {c['pending']}"
            + (f" (остаток {fmt(c['pending_outstanding'])} UZS)" if c["pending_outstanding"] else "")
        )
        if show_pending_list:
            for item in c["pending_items"][:10]:
                lines.append(f"  • {item}")
    return lines


def _money_block(title: str, money: dict) -> list[str]:
    lines = [f"💵 <b>{title}</b>"]
    if money["by_method"]:
        for label, amt in money["by_method"]:
            lines.append(f"  • {label}: {fmt(amt)}")
        lines.append(f"Итого по отчётам: <b>{fmt(money['total'])} UZS</b>")
    else:
        lines.append("По отчётам поступлений нет.")
    return lines


def _billz_block(entries: list[tuple[str, dict | None]]) -> list[str]:
    """XUSH (Billz) section showing several days: [(label, summary), ...]."""
    lines = ["🛍 <b>XUSH (Billz)</b>"]
    shown = False
    for label, billz in entries:
        if billz is None:
            continue
        shown = True
        if "error" in billz:
            lines.append(f"  • {label}: нет данных ⚠️")
            continue
        billz_total = float(billz["cash_total"] + billz["card_total"] + billz["other_total"])
        lines.append(
            f"  • {label}: <b>{fmt(billz_total)} UZS</b> — "
            f"наличные {fmt(billz['cash_total'])}, "
            f"карты {fmt(billz['card_total'])}, "
            f"прочее {fmt(billz['other_total'])} "
            f"({billz['order_count']} чек.)"
        )
    return lines if shown else []


def _iiko_block(entries: list[tuple[str, dict | None]]) -> list[str]:
    """Restaurant (iiko) section showing several days: [(label, summary), ...]."""
    lines = ["🍽 <b>Ресторан (iiko)</b>"]
    shown = False
    for label, s in entries:
        if s is None:
            continue
        shown = True
        if "error" in s:
            lines.append(f"  • {label}: нет данных ⚠️")
            continue
        split = ", ".join(f"{name} {fmt(amount)}" for name, amount in s["by_paytype"][:6])
        lines.append(f"  • {label}: <b>{fmt(s['total'])} UZS</b>" + (f" — {split}" if split else ""))
    return lines if shown else []


async def get_day_revenue_parts(target: date, billz: dict | None, iiko_s: dict | None) -> dict:
    """Overall revenue for a day: Resort (reports) + Restaurant (iiko, fallback
    reports) + XUSH (Billz, fallback reports). Reuses already-fetched Billz/iiko
    summaries to avoid duplicate API calls."""
    from db.enums import BusinessUnit

    resort = (await get_money_in(target, BusinessUnit.RESORT))["total"]

    if iiko_s and "error" not in iiko_s:
        restaurant, rest_src = float(iiko_s["total"]), "iiko"
    else:
        restaurant = (await get_money_in(target, BusinessUnit.RESTAURANT))["total"]
        rest_src = "отчёты"

    if billz and "error" not in billz:
        xush = float(billz["cash_total"] + billz["card_total"] + billz["other_total"])
        xush_src = "Billz"
    else:
        xush = (await get_money_in(target, BusinessUnit.XUSH))["total"]
        xush_src = "отчёты"

    return {
        "resort": resort,
        "restaurant": restaurant, "rest_src": rest_src,
        "xush": xush, "xush_src": xush_src,
        "total": resort + restaurant + xush,
    }


def _total_revenue_block(entries: list[tuple[str, dict]]) -> list[str]:
    """💰 Общая выручка section: [(day label, revenue parts), ...]."""
    lines = ["💰 <b>Общая выручка (курорт + ресторан + XUSH)</b>"]
    for label, p in entries:
        lines.append(f"  • {label}: <b>{fmt(p['total'])} UZS</b>")
        lines.append(
            f"      курорт {fmt(p['resort'])} · "
            f"ресторан {fmt(p['restaurant'])} ({p['rest_src']}) · "
            f"XUSH {fmt(p['xush'])} ({p['xush_src']})"
        )
    return lines


def _wallets_block(balances: list[tuple[str, float]]) -> list[str]:
    lines = ["👛 <b>Кошельки (наличные на руках)</b>"]
    if not balances:
        lines.append("Все кошельки пустые.")
        return lines
    for name, bal in balances:
        lines.append(f"  • {name}: {fmt(bal)}")
    lines.append(f"Итого на руках: <b>{fmt(sum(b for _, b in balances))} UZS</b>")
    return lines


# ── Digest builders ─────────────────────────────────────────────────


async def build_morning_digest(today: date) -> str:
    yesterday = today - timedelta(days=1)

    checkins_today = await get_checkins(today)
    checkins_yesterday = await get_checkins(yesterday)
    money_yesterday = await get_money_in(yesterday)
    billz_yesterday = await get_billz_summary(yesterday)
    billz_today = await get_billz_summary(today)
    iiko_yesterday = await iiko.get_daily_summary(yesterday)
    iiko_today = await iiko.get_daily_summary(today)
    balances = await get_wallet_balances()

    parts = [f"🌅 <b>Утренняя сводка — {today.strftime('%d.%m.%Y')}</b>", ""]
    parts += _checkins_block("Заезды сегодня", checkins_today)
    parts.append("")

    if checkins_yesterday["pending"]:
        parts.append(
            f"⚠️ <b>Вчерашние заезды без полной оплаты: {checkins_yesterday['pending']}</b>"
            + (
                f" (остаток {fmt(checkins_yesterday['pending_outstanding'])} UZS)"
                if checkins_yesterday["pending_outstanding"] else ""
            )
        )
        for item in checkins_yesterday["pending_items"][:10]:
            parts.append(f"  • {item}")
    else:
        parts.append("✅ Все вчерашние заезды полностью оплачены.")
    parts.append("")

    parts += _money_block(f"Деньги за вчера ({yesterday.strftime('%d.%m')})", money_yesterday)
    parts.append("")
    billz_lines = _billz_block([
        (f"вчера ({yesterday.strftime('%d.%m')})", billz_yesterday),
        (f"сегодня ({today.strftime('%d.%m')})", billz_today),
    ])
    if billz_lines:
        parts += billz_lines
        parts.append("")
    iiko_lines = _iiko_block([
        (f"вчера ({yesterday.strftime('%d.%m')})", iiko_yesterday),
        (f"сегодня ({today.strftime('%d.%m')})", iiko_today),
    ])
    if iiko_lines:
        parts += iiko_lines
        parts.append("")
    parts += _wallets_block(balances)
    parts.append("")

    rev_yesterday = await get_day_revenue_parts(yesterday, billz_yesterday, iiko_yesterday)
    rev_today = await get_day_revenue_parts(today, billz_today, iiko_today)
    parts += _total_revenue_block([
        (f"вчера ({yesterday.strftime('%d.%m')})", rev_yesterday),
        (f"сегодня ({today.strftime('%d.%m')})", rev_today),
    ])

    return "\n".join(parts)


async def build_evening_digest(today: date) -> str:
    yesterday = today - timedelta(days=1)

    checkins_today = await get_checkins(today)
    money_today = await get_money_in(today)
    billz_today = await get_billz_summary(today)
    billz_yesterday = await get_billz_summary(yesterday)
    iiko_today = await iiko.get_daily_summary(today)
    iiko_yesterday = await iiko.get_daily_summary(yesterday)
    balances = await get_wallet_balances()

    parts = [f"🌙 <b>Вечерняя сводка — {today.strftime('%d.%m.%Y')}</b>", ""]
    parts += _money_block("Деньги за сегодня", money_today)
    parts.append("")
    billz_lines = _billz_block([
        (f"сегодня ({today.strftime('%d.%m')})", billz_today),
        (f"вчера ({yesterday.strftime('%d.%m')})", billz_yesterday),
    ])
    if billz_lines:
        parts += billz_lines
        parts.append("")
    iiko_lines = _iiko_block([
        (f"сегодня ({today.strftime('%d.%m')})", iiko_today),
        (f"вчера ({yesterday.strftime('%d.%m')})", iiko_yesterday),
    ])
    if iiko_lines:
        parts += iiko_lines
        parts.append("")
    parts += _checkins_block("Заезды сегодня", checkins_today)
    parts.append("")
    parts += _wallets_block(balances)
    parts.append("")

    rev_today = await get_day_revenue_parts(today, billz_today, iiko_today)
    rev_yesterday = await get_day_revenue_parts(yesterday, billz_yesterday, iiko_yesterday)
    parts += _total_revenue_block([
        (f"сегодня ({today.strftime('%d.%m')})", rev_today),
        (f"вчера ({yesterday.strftime('%d.%m')})", rev_yesterday),
    ])

    return "\n".join(parts)


# ── Senders (scheduler entry points) ────────────────────────────────


async def _send_to_owners(bot: Bot, text: str) -> None:
    owner_ids = await _get_owner_ids()
    if not owner_ids:
        logger.warning("Owner digest: no active OWNER users found")
        return
    for tid in owner_ids:
        try:
            await bot.send_message(tid, text, parse_mode="HTML")
        except Exception as e:
            logger.error(f"Owner digest to {tid} failed: {e}")


async def send_morning_digest(bot: Bot) -> None:
    logger.info("Sending owner morning digest")
    try:
        text = await build_morning_digest(date.today())
        await _send_to_owners(bot, text)
    except Exception as e:
        logger.error(f"Morning digest failed: {e}", exc_info=True)


async def send_evening_digest(bot: Bot) -> None:
    logger.info("Sending owner evening digest")
    try:
        text = await build_evening_digest(date.today())
        await _send_to_owners(bot, text)
    except Exception as e:
        logger.error(f"Evening digest failed: {e}", exc_info=True)


# ── On-demand command: /svodka [вечер] (OWNER only) ─────────────────

router = Router()


async def _is_owner(telegram_id: int) -> bool:
    from db.enums import UserRole

    async with async_session() as session:
        role = (
            await session.execute(
                select(User.role).where(
                    User.telegram_id == telegram_id, User.is_active == True
                )
            )
        ).scalar_one_or_none()
    return role == UserRole.OWNER


@router.message(Command("svodka"))
async def cmd_svodka(message: types.Message, command: CommandObject):
    """/svodka — morning-style digest now; /svodka вечер — evening-style."""
    if not await _is_owner(message.from_user.id):
        return
    await message.answer("⏳ Готовлю сводку...")
    arg = (command.args or "").strip().lower()
    try:
        if arg in ("вечер", "evening", "v", "e"):
            text = await build_evening_digest(date.today())
        else:
            text = await build_morning_digest(date.today())
        await message.answer(text, parse_mode="HTML")
    except Exception as e:
        logger.error(f"/svodka failed: {e}", exc_info=True)
        await message.answer(f"⚠️ Не удалось построить сводку: {e}")
