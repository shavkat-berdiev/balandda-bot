"""iiko cash → restaurant manager wallet sync.

Process change (2026-07-24): restaurant cash revenue is no longer entered
manually as report income (that double-counted against the iiko integration).
Instead, every day the iiko cash total is credited to the restaurant manager's
cash wallet (CASH_IN), and he hands it over / does инкассация like everyone else.

Runs:
  • 23:30 — credit today's iiko cash
  • 08:50 next day — top-up delta for late cheques (before the morning digest)

Idempotent: each day's credited amount is tracked via a [iiko-sync:YYYY-MM-DD]
marker in the transaction note; only the positive delta is ever added.
"""

import logging
from datetime import date, timedelta
from decimal import Decimal

from aiogram import Bot, Router, types
from aiogram.filters import Command, CommandObject
from sqlalchemy import func, select

from bot.config import settings
from bot.notifications import _get_owner_ids
from db.database import async_session
from db.enums import BusinessUnit, WalletTransactionStatus, WalletTransactionType
from db.models import User, WalletTransaction
from services import iiko

logger = logging.getLogger(__name__)

CASH_KEYWORDS = ("наличн", "cash", "naqd")


def _marker(target: date) -> str:
    return f"[iiko-sync:{target.isoformat()}]"


async def get_iiko_cash_total(target: date) -> float | None:
    """iiko cash revenue for a date; None if iiko unavailable/not configured."""
    s = await iiko.get_daily_summary(target)
    if s is None or "error" in s:
        return None
    return float(sum(
        amount for name, amount in s["by_paytype"]
        if any(kw in name.lower() for kw in CASH_KEYWORDS)
    ))


async def _already_credited(target: date) -> float:
    async with async_session() as session:
        total = (
            await session.execute(
                select(func.coalesce(func.sum(WalletTransaction.amount), 0)).where(
                    WalletTransaction.sender_telegram_id == settings.iiko_cash_wallet_id,
                    WalletTransaction.transaction_type == WalletTransactionType.CASH_IN,
                    WalletTransaction.status == WalletTransactionStatus.COMPLETED,
                    WalletTransaction.note.like(f"%{_marker(target)}%"),
                )
            )
        ).scalar()
    return float(total or 0)


async def sync_iiko_cash(bot: Bot | None, target: date) -> dict:
    """Credit the (delta of the) day's iiko cash to the manager's wallet.

    Returns {"date", "cash_total", "already", "credited"} for reporting.
    """
    wallet_id = settings.iiko_cash_wallet_id
    if not wallet_id or not iiko.is_configured():
        return {"date": target.isoformat(), "cash_total": None, "already": 0, "credited": 0}

    cash_total = await get_iiko_cash_total(target)
    if cash_total is None:
        logger.warning(f"iiko cash sync: no data for {target}")
        return {"date": target.isoformat(), "cash_total": None, "already": 0, "credited": 0}

    already = await _already_credited(target)
    delta = round(cash_total - already)

    if delta <= 0:
        logger.info(f"iiko cash sync {target}: nothing to credit (total {cash_total}, already {already})")
        return {"date": target.isoformat(), "cash_total": cash_total, "already": already, "credited": 0}

    async with async_session() as session:
        session.add(WalletTransaction(
            sender_telegram_id=wallet_id,
            amount=Decimal(delta),
            transaction_type=WalletTransactionType.CASH_IN,
            status=WalletTransactionStatus.COMPLETED,
            note=f"Наличная выручка iiko за {target.strftime('%d.%m.%Y')} {_marker(target)}",
            business_unit=BusinessUnit.RESTAURANT,
        ))
        await session.commit()

        manager_name = (
            await session.execute(
                select(User.full_name).where(User.telegram_id == wallet_id)
            )
        ).scalar_one_or_none() or str(wallet_id)

    logger.info(f"iiko cash sync {target}: credited {delta} to {manager_name}")

    if bot is not None:
        def _fmt(a):
            return f"{float(a):,.0f}".replace(",", ".")

        text = (
            f"💵 <b>Наличные iiko → кошелёк</b>\n\n"
            f"📅 {target.strftime('%d.%m.%Y')}\n"
            f"💰 Зачислено: <b>{_fmt(delta)} UZS</b>"
            + (f" (доначисление, всего за день {_fmt(cash_total)})" if already > 0 else "")
            + f"\n👤 {manager_name}\n\n"
            f"Не забудьте передать наличные или сделать инкассацию."
        )
        # The manager himself
        try:
            await bot.send_message(wallet_id, text, parse_mode="HTML")
        except Exception as e:
            logger.error(f"iiko cash sync: notify manager {wallet_id} failed: {e}")
        # Owners (FYI) — via the Reporting group topic if bound, else DMs
        from bot.notifications import CAT_INKASSATSIYA, send_via_route

        if not await send_via_route(bot, CAT_INKASSATSIYA, text):
            for tid in await _get_owner_ids():
                try:
                    await bot.send_message(tid, text, parse_mode="HTML")
                except Exception as e:
                    logger.error(f"iiko cash sync: notify owner {tid} failed: {e}")

    return {"date": target.isoformat(), "cash_total": cash_total, "already": already, "credited": delta}


# ── Scheduler entry points ──────────────────────────────────────────


async def sync_today(bot: Bot) -> None:
    try:
        await sync_iiko_cash(bot, date.today())
    except Exception as e:
        logger.error(f"iiko cash sync (today) failed: {e}", exc_info=True)


async def sync_yesterday(bot: Bot) -> None:
    """Morning top-up for late cheques — runs before the 09:00 digest."""
    try:
        await sync_iiko_cash(bot, date.today() - timedelta(days=1))
    except Exception as e:
        logger.error(f"iiko cash sync (yesterday) failed: {e}", exc_info=True)


# ── On-demand command: /iiko_sync [вчера] (OWNER or manager) ───────

router = Router()


@router.message(Command("iiko_sync"))
async def cmd_iiko_sync(message: types.Message, command: CommandObject):
    from bot.owner_digest import _is_owner

    uid = message.from_user.id
    if uid != settings.iiko_cash_wallet_id and not await _is_owner(uid):
        return

    arg = (command.args or "").strip().lower()
    target = date.today() - timedelta(days=1) if arg in ("вчера", "yesterday", "v") else date.today()

    await message.answer("⏳ Синхронизирую наличные iiko...")
    try:
        r = await sync_iiko_cash(message.bot, target)
    except Exception as e:
        logger.error(f"/iiko_sync failed: {e}", exc_info=True)
        await message.answer(f"⚠️ Ошибка синхронизации: {e}")
        return

    def _fmt(a):
        return f"{float(a):,.0f}".replace(",", ".")

    if r["cash_total"] is None:
        await message.answer("⚠️ Нет данных iiko (не настроено или недоступно).")
    elif r["credited"] == 0:
        await message.answer(
            f"✅ Уже синхронизировано за {target.strftime('%d.%m.%Y')}: "
            f"наличные iiko {_fmt(r['cash_total'])} UZS, зачислено ранее {_fmt(r['already'])} UZS."
        )
    else:
        await message.answer(
            f"✅ Зачислено {_fmt(r['credited'])} UZS за {target.strftime('%d.%m.%Y')}."
        )
