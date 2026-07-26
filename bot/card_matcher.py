"""Match incoming card transfers (CardTransaction) to team-reported entries.

BALANDDA card: matched against
  - IncomeEntry with payment_method=CARD_TRANSFER (resort + restaurant reports)
  - Prepayment rows (payment method CARD_TRANSFER)
by exact amount within a ±36h window, closest-in-time first, one entry per
transaction. XUSH is reconciled as daily totals against Billz (see card_recon).

Statuses: NEW (just arrived) → MATCHED / UNMATCHED (no candidate found yet;
retried on every run until the transaction is older than 3 days) / IGNORED
(dismissed manually via the web UI).
"""

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from db.database import async_session
from db.enums import PaymentMethod
from db.models import CardTransaction, IncomeEntry, Prepayment, StructuredReport

logger = logging.getLogger(__name__)

MATCH_WINDOW = timedelta(hours=36)
RETRY_DAYS = 3  # keep retrying unmatched transactions this long


def _entry_time(entry: IncomeEntry, report: StructuredReport) -> datetime:
    """Best-effort timestamp for an income entry."""
    created = getattr(entry, "created_at", None)
    if created is not None:
        return created
    # Fallback: middle of the report date (12:00 UTC ≈ 17:00 Tashkent)
    d = report.report_date
    return datetime(d.year, d.month, d.day, 12, 0, tzinfo=timezone.utc)


async def run_matching() -> dict:
    """One matching pass. Returns counters for logging/reporting."""
    now = datetime.now(timezone.utc)
    horizon = now - timedelta(days=RETRY_DAYS)
    stats = {"matched": 0, "unmatched": 0}

    async with async_session() as session:
        txs = (
            await session.execute(
                select(CardTransaction)
                .where(
                    CardTransaction.direction == "IN",
                    CardTransaction.business == "BALANDDA",
                    CardTransaction.match_status.in_(["NEW", "UNMATCHED"]),
                    CardTransaction.tx_time >= horizon,
                )
                .order_by(CardTransaction.tx_time)
            )
        ).scalars().all()

        if not txs:
            return stats

        # Entry ids already claimed by other card transactions
        used = (
            await session.execute(
                select(CardTransaction.matched_type, CardTransaction.matched_id).where(
                    CardTransaction.matched_id.is_not(None)
                )
            )
        ).all()
        used_entries = {(t, i) for t, i in used}

        t_min = min(t.tx_time for t in txs) - MATCH_WINDOW
        t_max = max(t.tx_time for t in txs) + MATCH_WINDOW

        # Candidate income entries (card transfers) in the window
        entry_rows = (
            await session.execute(
                select(IncomeEntry, StructuredReport)
                .join(StructuredReport, IncomeEntry.report_id == StructuredReport.id)
                .where(
                    IncomeEntry.payment_method == PaymentMethod.CARD_TRANSFER,
                    StructuredReport.report_date >= (t_min.date() - timedelta(days=1)),
                    StructuredReport.report_date <= (t_max.date() + timedelta(days=1)),
                )
            )
        ).all()

        # Candidate prepayments in the window
        prepay_rows = (
            await session.execute(
                select(Prepayment).where(
                    Prepayment.created_at >= t_min,
                    Prepayment.created_at <= t_max,
                )
            )
        ).scalars().all()

        candidates: list[tuple[str, int, float, datetime]] = []
        for entry, report in entry_rows:
            candidates.append(
                ("income_entry", entry.id, float(entry.amount), _entry_time(entry, report))
            )
        for p in prepay_rows:
            # A calendar prepayment mirrors an IncomeEntry (income_entry_id set) —
            # that entry is already a candidate; skip the duplicate row so one
            # real payment can't match two different card transactions.
            if p.income_entry_id:
                continue
            pm = (p.payment_method or "").upper()
            if "CARD" in pm or "PEREVOD" in pm:
                candidates.append(("prepayment", p.id, float(p.amount), p.created_at))

        for tx in txs:
            best = None
            best_dt = None
            for ctype, cid, camount, ctime in candidates:
                if (ctype, cid) in used_entries:
                    continue
                if abs(camount - float(tx.amount)) > 0.01:
                    continue
                delta = abs((ctime - tx.tx_time).total_seconds())
                if delta > MATCH_WINDOW.total_seconds():
                    continue
                if best_dt is None or delta < best_dt:
                    best = (ctype, cid)
                    best_dt = delta
            if best:
                tx.match_status = "MATCHED"
                tx.matched_type, tx.matched_id = best
                used_entries.add(best)
                stats["matched"] += 1
            else:
                tx.match_status = "UNMATCHED"
                stats["unmatched"] += 1

        await session.commit()

    if stats["matched"] or stats["unmatched"]:
        logger.info(f"Card matching: {stats['matched']} matched, {stats['unmatched']} unmatched")
    return stats
