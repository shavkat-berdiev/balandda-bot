"""Settle stale PENDING wallet transfers that were already reconciled on paper.

The problem
───────────
`WalletTransactionStatus.PENDING` deducts from the sender and credits nobody —
the money is frozen until the receiver taps ✅. Balandda accumulated 26 such
transfers to Azizov (≈215M UZS, back to 2026-04) that will never be accepted in
the bot, because he received that cash and accounted for it on paper under the
old reporting process.

What "settle" means here
────────────────────────
NOT a plain accept. Flipping PENDING → COMPLETED alone would credit the receiver
the full amount, because the balance formula counts incoming transfers only when
COMPLETED. That money is not his — it was already accounted for outside the bot.

So this script does both halves:

  1. PENDING → COMPLETED   — records that he did in fact receive the cash.
  2. one offsetting ADJUSTMENT of −total on the receiver — writes it straight
     back off as "already reconciled on paper".

Net effect on every balance in the system: **zero**.
  · Sender   — outgoing counts PENDING and COMPLETED alike, so unchanged.
  · Receiver — +total from the accepts, −total from the adjustment.
It only drains the pending queue, which is the point.

Why not CANCELLED / REVERSED
────────────────────────────
Both drop the transfer out of the sender's outgoing sum, handing every sender
back money they genuinely no longer have — inflating balances by the full total.
That is the one outcome to avoid here.

Usage — inside the bot container, dry run first:

    docker compose exec bot python scripts/settle_pending_transfers.py
    docker compose exec bot python scripts/settle_pending_transfers.py --receiver <telegram_id>
    docker compose exec bot python scripts/settle_pending_transfers.py --receiver <telegram_id> --apply

With no --receiver it only surveys who has stale pending incoming.
Nothing is written unless --apply is passed. Re-running is safe: it refuses to
double-settle, and with no PENDING rows left there is nothing to do.
"""

import argparse
import asyncio
import os
import sys
from decimal import Decimal

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import and_, func, or_, select

from db.database import async_session
from db.models import User, WalletTransaction
from db.enums import WalletTransactionStatus, WalletTransactionType

# Marker written into the offsetting adjustment so a second run can spot it.
MARKER = "[settle-pending]"

TRANSFER_TYPES = (
    WalletTransactionType.TRANSFER_TO_EMPLOYEE,
    WalletTransactionType.TRANSFER_TO_SHAVKAT,
)


def money(v) -> str:
    return f"{Decimal(str(v or 0)):,.0f}".replace(",", " ")


async def balance(session, tid: int) -> Decimal:
    """Same formula as bot/handlers/wallet.py::get_wallet_balance."""
    incoming = await session.execute(
        select(func.coalesce(func.sum(WalletTransaction.amount), 0)).where(or_(
            and_(WalletTransaction.sender_telegram_id == tid,
                 WalletTransaction.transaction_type == WalletTransactionType.CASH_IN,
                 WalletTransaction.status == WalletTransactionStatus.COMPLETED),
            and_(WalletTransaction.receiver_telegram_id == tid,
                 WalletTransaction.transaction_type == WalletTransactionType.TRANSFER_TO_EMPLOYEE,
                 WalletTransaction.status == WalletTransactionStatus.COMPLETED),
        )))
    outgoing = await session.execute(
        select(func.coalesce(func.sum(WalletTransaction.amount), 0)).where(
            WalletTransaction.sender_telegram_id == tid,
            WalletTransaction.transaction_type.in_([
                WalletTransactionType.TRANSFER_TO_EMPLOYEE,
                WalletTransactionType.TRANSFER_TO_SHAVKAT,
                WalletTransactionType.CASH_TO_BANK,
                WalletTransactionType.PURCHASE,
                WalletTransactionType.SALARY,
                WalletTransactionType.EXPENSE,
            ]),
            WalletTransaction.status.in_([WalletTransactionStatus.PENDING,
                                          WalletTransactionStatus.COMPLETED])))
    adj = await session.execute(
        select(func.coalesce(func.sum(WalletTransaction.amount), 0)).where(
            WalletTransaction.sender_telegram_id == tid,
            WalletTransaction.transaction_type == WalletTransactionType.ADJUSTMENT,
            WalletTransaction.status == WalletTransactionStatus.COMPLETED))
    return (Decimal(str(incoming.scalar())) - Decimal(str(outgoing.scalar()))
            + Decimal(str(adj.scalar())))


async def names(session, ids):
    if not ids:
        return {}
    rows = (await session.execute(select(User).where(User.telegram_id.in_(list(ids))))).scalars().all()
    return {u.telegram_id: u.full_name for u in rows}


async def survey(session):
    """Who is sitting on stale pending incoming transfers."""
    rows = (await session.execute(
        select(WalletTransaction)
        .where(WalletTransaction.status == WalletTransactionStatus.PENDING,
               WalletTransaction.transaction_type.in_(TRANSFER_TYPES))
    )).scalars().all()

    if not rows:
        print("No pending transfers anywhere. Nothing to settle.")
        return

    by_receiver = {}
    for t in rows:
        acc = by_receiver.setdefault(t.receiver_telegram_id, [0, Decimal(0), None, None])
        acc[0] += 1
        acc[1] += Decimal(str(t.amount))
        d = t.created_at.date() if t.created_at else None
        if d and (acc[2] is None or d < acc[2]):
            acc[2] = d
        if d and (acc[3] is None or d > acc[3]):
            acc[3] = d

    who = await names(session, by_receiver.keys())
    print(f"\nPending transfers by receiver ({len(rows)} total):\n")
    print(f"  {'receiver':<28} {'tg_id':>12} {'n':>4} {'amount':>18}   period")
    print("  " + "-" * 84)
    for tid, (n, total, first, last) in sorted(by_receiver.items(), key=lambda kv: -kv[1][1]):
        label = who.get(tid, "(unknown)")
        print(f"  {label:<28} {tid:>12} {n:>4} {money(total):>18}   {first} → {last}")
    print("\nRe-run with --receiver <tg_id> to see the detail for one person.")


async def settle(session, receiver_id: int, apply: bool, reason: str):
    rows = (await session.execute(
        select(WalletTransaction)
        .where(WalletTransaction.receiver_telegram_id == receiver_id,
               WalletTransaction.status == WalletTransactionStatus.PENDING,
               WalletTransaction.transaction_type.in_(TRANSFER_TYPES))
        .order_by(WalletTransaction.created_at)
    )).scalars().all()

    who = await names(session, {receiver_id} | {t.sender_telegram_id for t in rows})
    receiver_name = who.get(receiver_id, "(unknown)")

    if not rows:
        print(f"\n{receiver_name} ({receiver_id}) has no pending incoming transfers. Nothing to do.")
        return

    # Guard: has a previous run already written an offset for this person?
    prior = (await session.execute(
        select(func.count()).where(
            WalletTransaction.sender_telegram_id == receiver_id,
            WalletTransaction.transaction_type == WalletTransactionType.ADJUSTMENT,
            WalletTransaction.note.like(f"%{MARKER}%"))
    )).scalar()
    if prior:
        print(f"\n!! {receiver_name} already has {prior} '{MARKER}' adjustment(s).")
        print("   Refusing to run again — inspect manually before forcing anything.")
        return

    total = sum((Decimal(str(t.amount)) for t in rows), Decimal(0))

    print(f"\nReceiver: {receiver_name} ({receiver_id})")
    print(f"Pending transfers to settle: {len(rows)}   total {money(total)} UZS\n")
    print(f"  {'id':>6}  {'date':<12} {'from':<26} {'amount':>16}")
    print("  " + "-" * 66)
    for t in rows:
        d = t.created_at.date().isoformat() if t.created_at else "—"
        print(f"  {t.id:>6}  {d:<12} {who.get(t.sender_telegram_id, '?'):<26} {money(t.amount):>16}")

    senders = sorted({t.sender_telegram_id for t in rows})
    before = {tid: await balance(session, tid) for tid in senders + [receiver_id]}

    print(f"\nBalances before:")
    for tid in senders + [receiver_id]:
        tag = " (receiver)" if tid == receiver_id else ""
        print(f"  {who.get(tid, '?'):<26} {money(before[tid]):>18} UZS{tag}")

    print(f"\nPlan:")
    print(f"  1. {len(rows)} transfers PENDING → COMPLETED")
    print(f"  2. one ADJUSTMENT of −{money(total)} UZS on {receiver_name}")
    print(f"     note: «{reason} {MARKER}»")
    print(f"  Expected net change for EVERY wallet: 0")

    if not apply:
        print("\nDRY RUN — nothing written. Re-run with --apply to commit.")
        return

    for t in rows:
        t.status = WalletTransactionStatus.COMPLETED
        stamp = f"Автопринятие: {reason} {MARKER}"
        t.note = f"{t.note} · {stamp}" if t.note else stamp
        t.note = t.note[:2000]

    session.add(WalletTransaction(
        sender_telegram_id=receiver_id,
        amount=-total,
        transaction_type=WalletTransactionType.ADJUSTMENT,
        status=WalletTransactionStatus.COMPLETED,
        note=f"{reason} — списание {len(rows)} переводов на {money(total)} UZS {MARKER}"[:2000],
    ))
    await session.commit()

    after = {tid: await balance(session, tid) for tid in senders + [receiver_id]}
    print(f"\nBalances after:")
    ok = True
    for tid in senders + [receiver_id]:
        delta = after[tid] - before[tid]
        if delta != 0:
            ok = False
        flag = "  OK" if delta == 0 else f"  !! CHANGED BY {money(delta)}"
        print(f"  {who.get(tid, '?'):<26} {money(after[tid]):>18} UZS{flag}")

    left = (await session.execute(
        select(func.count()).where(
            WalletTransaction.receiver_telegram_id == receiver_id,
            WalletTransaction.status == WalletTransactionStatus.PENDING,
            WalletTransaction.transaction_type.in_(TRANSFER_TYPES))
    )).scalar()

    print(f"\nPending inbox for {receiver_name}: {left} (was {len(rows)})")
    print("DONE — every balance unchanged, queue cleared." if ok and left == 0
          else "!! Unexpected result — review before trusting this.")


async def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--receiver", type=int, help="telegram_id whose pending inbox to settle")
    ap.add_argument("--apply", action="store_true", help="actually write (default is dry run)")
    ap.add_argument("--reason", default="учтено в бумажных отчётах до перехода на бота")
    args = ap.parse_args()

    async with async_session() as session:
        if args.receiver is None:
            await survey(session)
        else:
            await settle(session, args.receiver, args.apply, args.reason)


asyncio.run(main())
