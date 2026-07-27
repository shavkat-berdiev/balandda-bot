"""Daily card reconciliation — one evening post per business into its topic.

BALANDDA (*4042): incoming transfers vs reported card-transfer entries
  (per-transaction matching, see bot/card_matcher.py)
XUSH (*8044): incoming transfers total vs Billz per-payment-type sales
  (daily totals — Billz is the source of truth for XUSH sales)

Reconciliation summaries go to OWNER users' PRIVATE chats only (owner-facing
control data). The CARD_BALANDDA / CARD_XUSH topic bindings are used solely by
the real-time per-transfer posts in bot/card_reader.py.
"""

import logging
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from aiogram import Bot
from sqlalchemy import select

from bot import billz, card_matcher
from bot.config import settings
from bot.notifications import _send_to_owners
from db.database import async_session
from db.models import CardTransaction

logger = logging.getLogger(__name__)

_TZ = ZoneInfo("Asia/Tashkent")


def _fmt(amount: float) -> str:
    return f"{amount:,.0f}".replace(",", " ")


async def _day_transactions(business: str, day: date) -> list[CardTransaction]:
    start = datetime.combine(day, time.min, tzinfo=_TZ)
    end = start + timedelta(days=1)
    async with async_session() as session:
        return (
            await session.execute(
                select(CardTransaction)
                .where(
                    CardTransaction.business == business,
                    CardTransaction.direction == "IN",
                    CardTransaction.tx_time >= start,
                    CardTransaction.tx_time < end,
                    CardTransaction.match_status != "IGNORED",
                )
                .order_by(CardTransaction.tx_time)
            )
        ).scalars().all()


def _tx_line(tx: CardTransaction) -> str:
    t = tx.tx_time.astimezone(_TZ).strftime("%H:%M")
    src = (tx.merchant or "").split(",")[0][:28]
    return f"  • {t} — {_fmt(float(tx.amount))} UZS ({src})"


async def build_balandda_recon(day: date) -> str:
    txs = await _day_transactions("BALANDDA", day)
    matched = [t for t in txs if t.match_status == "MATCHED"]
    unmatched = [t for t in txs if t.match_status in ("NEW", "UNMATCHED")]
    total = sum(float(t.amount) for t in txs)

    lines = [
        f"💳 <b>Сверка переводов Balandda (*{_balandda_last4()}) — {day.strftime('%d.%m.%Y')}</b>",
        "",
        f"Поступило: <b>{_fmt(total)} UZS</b> ({len(txs)} перевод(ов))",
        f"✅ Совпало с отчётами: {len(matched)}",
    ]
    if unmatched:
        lines.append(f"⚠️ <b>Без отчёта: {len(unmatched)} на {_fmt(sum(float(t.amount) for t in unmatched))} UZS</b>")
        lines.extend(_tx_line(t) for t in unmatched)
        lines.append("")
        lines.append("Проверьте: эти переводы пришли на карту, но не найдены в отчётах.")
    elif txs:
        lines.append("Все поступления сверены с отчётами 👍")
    else:
        lines.append("Поступлений на карту сегодня не было.")
    return "\n".join(lines)


async def build_xush_recon(day: date) -> str:
    txs = await _day_transactions("XUSH", day)
    total = sum(float(t.amount) for t in txs)

    lines = [
        f"💳 <b>Сверка переводов XUSH (*{_xush_last4()}) — {day.strftime('%d.%m.%Y')}</b>",
        "",
        f"Поступило на карту: <b>{_fmt(total)} UZS</b> ({len(txs)} перевод(ов))",
    ]
    if txs:
        lines.extend(_tx_line(t) for t in txs)

    # Billz side — per-payment-type totals for the day
    try:
        rows = await billz.get_range_daily(day, day)
        day_rows = [r for r in rows if r["date"] == day.isoformat()]
        if day_rows:
            lines.append("")
            lines.append("Billz (продажи по типам оплат):")
            for r in sorted(day_rows, key=lambda r: -r["amount"]):
                lines.append(f"  • {r['pay_type']}: {_fmt(r['amount'])} UZS")
            lines.append("")
            lines.append("Сравните сумму переводов на карту с соответствующим типом оплаты в Billz.")
        elif billz.is_configured():
            lines.append("")
            lines.append("Billz: продаж за день не найдено.")
    except Exception as e:
        logger.warning(f"XUSH recon: Billz unavailable: {e}")
        lines.append("")
        lines.append("⚠️ Billz недоступен — сверка только по карте.")

    if not txs:
        lines.append("Поступлений на карту сегодня не было.")
    return "\n".join(lines)


def _balandda_last4() -> str:
    for last4, biz in settings.card_business_map.items():
        if biz == "BALANDDA":
            return last4
    return "????"


def _xush_last4() -> str:
    for last4, biz in settings.card_business_map.items():
        if biz == "XUSH":
            return last4
    return "????"


async def send_daily_reconciliation(bot: Bot):
    """Evening job: refresh matching, then DM one summary per business to owners."""
    day = datetime.now(_TZ).date()
    try:
        await card_matcher.run_matching()
    except Exception as e:
        logger.error(f"Card matching failed before reconciliation: {e}", exc_info=True)

    try:
        await _send_to_owners(bot, await build_balandda_recon(day))
    except Exception as e:
        logger.error(f"Balandda card reconciliation failed: {e}", exc_info=True)

    try:
        await _send_to_owners(bot, await build_xush_recon(day))
    except Exception as e:
        logger.error(f"XUSH card reconciliation failed: {e}", exc_info=True)
