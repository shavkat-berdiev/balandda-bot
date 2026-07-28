"""SPA commission ledger — shared by the API (Комиссии page), the SPA bot
(admin payout menu) and the daily digest.

Rules (decided 2026-07-28):
- Commission is EARNED when an appointment is marked status='done'.
- The amount is the service's fixed UZS sum picked by the master's type
  (commission_internal / commission_external).
- A payout deducts from the payer's analytics cash wallet as a SALARY-type
  wallet transaction and is recorded in spa_commission_payouts.
- Balance (к выплате) = all-time earned − all-time paid out.
"""

from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from db.models import (
    ServiceItem,
    SpaAppointment,
    SpaCommissionPayout,
    SpaMaster,
    WalletTransaction,
    WalletTransactionStatus,
    WalletTransactionType,
)

TASHKENT = timezone(timedelta(hours=5))


def commission_amount(svc: ServiceItem | None, master: SpaMaster | None) -> float:
    if not svc:
        return 0.0
    if master and (master.master_type or "internal") == "external":
        return float(svc.commission_external or 0)
    return float(svc.commission_internal or 0)


def day_bounds(d: date) -> tuple[datetime, datetime]:
    start = datetime.combine(d, time.min, tzinfo=TASHKENT)
    return start, start + timedelta(days=1)


async def done_appointments(session, start: datetime, end: datetime, master_id: int | None = None):
    """Done appointments in [start, end) with service+master loaded."""
    stmt = (
        select(SpaAppointment)
        .options(
            selectinload(SpaAppointment.service),
            selectinload(SpaAppointment.master),
            selectinload(SpaAppointment.location),
        )
        .where(
            SpaAppointment.status == "done",
            SpaAppointment.start_at >= start,
            SpaAppointment.start_at < end,
        )
        .order_by(SpaAppointment.start_at)
    )
    if master_id:
        stmt = stmt.where(SpaAppointment.master_id == master_id)
    return (await session.execute(stmt)).scalars().all()


async def earned_in_period(session, start: datetime, end: datetime, master_id: int) -> float:
    appts = await done_appointments(session, start, end, master_id)
    return sum(commission_amount(a.service, a.master) for a in appts)


async def paid_in_period(session, master_id: int, start: datetime | None = None, end: datetime | None = None) -> float:
    stmt = select(func.coalesce(func.sum(SpaCommissionPayout.amount), 0)).where(
        SpaCommissionPayout.master_id == master_id
    )
    if start is not None:
        stmt = stmt.where(SpaCommissionPayout.created_at >= start)
    if end is not None:
        stmt = stmt.where(SpaCommissionPayout.created_at < end)
    return float((await session.execute(stmt)).scalar() or 0)


async def earned_alltime(session, master_id: int) -> float:
    """All-time earned; computed in Python because the amount depends on
    service commission × master type (no stored per-appointment amount)."""
    appts = (
        await session.execute(
            select(SpaAppointment)
            .options(selectinload(SpaAppointment.service), selectinload(SpaAppointment.master))
            .where(SpaAppointment.status == "done", SpaAppointment.master_id == master_id)
        )
    ).scalars().all()
    return sum(commission_amount(a.service, a.master) for a in appts)


async def master_balance(session, master_id: int) -> float:
    return await earned_alltime(session, master_id) - await paid_in_period(session, master_id)


async def summary(session, start: datetime, end: datetime) -> list[dict]:
    """Per-master commission summary for a period + all-time balance."""
    masters = (
        await session.execute(select(SpaMaster).order_by(SpaMaster.sort_order, SpaMaster.name))
    ).scalars().all()
    appts = await done_appointments(session, start, end)
    out = []
    for m in masters:
        mine = [a for a in appts if a.master_id == m.id]
        earned = sum(commission_amount(a.service, a.master) for a in mine)
        paid = await paid_in_period(session, m.id, start, end)
        balance = await master_balance(session, m.id)
        if not mine and not paid and not balance and not m.is_active:
            continue  # hide inactive masters with no activity
        out.append({
            "master_id": m.id,
            "name": m.name,
            "master_type": m.master_type or "internal",
            "is_active": m.is_active,
            "services_done": len(mine),
            "revenue": sum(float(a.price or 0) for a in mine),
            "earned": earned,
            "paid_in_period": paid,
            "balance": balance,
        })
    return out


async def create_payout(session, master_id: int, amount: float, paid_by: int, note: str | None = None):
    """Record a payout: ledger row + SALARY wallet deduction from the payer.
    Caller commits. Returns (payout, wallet_tx). Raises ValueError on bad amount."""
    if amount <= 0:
        raise ValueError("Сумма выплаты должна быть больше нуля")
    master = await session.get(SpaMaster, master_id)
    if not master:
        raise ValueError("Мастер не найден")
    balance = await master_balance(session, master_id)
    if amount > balance + 0.01:
        raise ValueError(f"Сумма превышает остаток к выплате ({balance:,.0f} UZS)")
    tx = WalletTransaction(
        sender_telegram_id=paid_by,
        amount=Decimal(str(round(amount))),
        transaction_type=WalletTransactionType.SALARY,
        status=WalletTransactionStatus.COMPLETED,
        note=f"Комиссия SPA: {master.name}" + (f" — {note}" if note else ""),
    )
    session.add(tx)
    await session.flush()
    payout = SpaCommissionPayout(
        master_id=master_id, amount=Decimal(str(round(amount))),
        paid_by=paid_by, note=note, wallet_tx_id=tx.id,
    )
    session.add(payout)
    await session.flush()
    return payout, tx
