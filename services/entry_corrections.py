"""Correcting a mistyped income/expense entry — and unwinding a wrong transfer.

Why this module exists
──────────────────────
Before 2026-08 there was no correct way to fix a mistyped amount:

* The bot had no edit path at all. Staff worked around it by filing an
  `ExpenseCategory.REFUND` entry, believing «возвраты» would credit the money
  back — but REFUND falls through to `WalletTransactionType.EXPENSE`, so it
  deducted a *second* time. That is what drove Наргис's wallet to −8,990,448
  after a 10× typo (1,260,000 typed as 12,600,000).
* The owner-only web endpoints (`PUT/DELETE /structured-reports/*-entry/{id}`)
  recomputed the report totals but posted **no** wallet transaction, so the
  ledger stayed wrong even after the owner "fixed" the report.

Everything now goes through this module, so the bot and the dashboard cannot
drift apart again.

The rule
────────
**Nothing is ever silently rewritten.** The entry's amount changes, and a
signed `ADJUSTMENT` wallet transaction is posted for the *cash delta* — the same
pattern `api/routers/reservations.py` already used correctly. History therefore
always shows what happened, and `wallet_diag.sql` style reconciliation keeps
adding up (any query over wallets MUST include ADJUSTMENT rows).

Which wallet gets adjusted
──────────────────────────
The one that was actually credited/debited — read from `entry.wallet_tx_id`.
This matters for Mini shop, where the CASH_IN belongs to the configured seller
rather than whoever typed the sale in. Rows created before that column existed
fall back to `report.submitted_by`.

Only cash moves a wallet. Editing a CARD_TRANSFER entry changes the report
total and nothing else; switching a payment method between cash and non-cash
adjusts by the full amount in the right direction.
"""

import logging
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.enums import (
    PaymentMethod,
    ReportStatus,
    WalletTransactionStatus,
    WalletTransactionType,
)
from db.models import (
    ExpenseEntry,
    IncomeEntry,
    StructuredReport,
    WalletTransaction,
)

logger = logging.getLogger(__name__)


class CorrectionError(Exception):
    """Raised when a correction is not allowed. The message is user-facing."""


@dataclass
class CorrectionResult:
    """What changed — callers use this to build the notification text."""
    entry_id: int
    report_id: int
    kind: str                 # "income" | "expense"
    label: str                # human name of what was corrected
    old_amount: Decimal
    new_amount: Decimal | None   # None → the entry was deleted
    wallet_delta: Decimal     # signed change applied to the wallet (0 = non-cash)
    wallet_owner: int | None  # telegram_id whose wallet moved

    @property
    def deleted(self) -> bool:
        return self.new_amount is None


def _q(value) -> Decimal:
    return Decimal(str(value or 0))


async def _wallet_owner_for(session: AsyncSession, entry, report: StructuredReport | None) -> int | None:
    """Whose wallet this entry moved.

    Prefers the linked transaction (correct for Mini shop, where the seller is
    not the recorder); falls back to the report submitter for rows created
    before `wallet_tx_id` existed.
    """
    tx_id = getattr(entry, "wallet_tx_id", None)
    if tx_id:
        tx = await session.get(WalletTransaction, tx_id)
        if tx is not None:
            return tx.sender_telegram_id
    return report.submitted_by if report is not None else None


async def _post_adjustment(
    session: AsyncSession,
    *,
    telegram_id: int | None,
    delta: Decimal,
    report: StructuredReport | None,
    note: str,
) -> None:
    """Post a signed ADJUSTMENT. Positive = wallet gains, negative = wallet loses."""
    if not telegram_id or delta == 0:
        return
    session.add(WalletTransaction(
        sender_telegram_id=telegram_id,
        amount=delta,
        transaction_type=WalletTransactionType.ADJUSTMENT,
        status=WalletTransactionStatus.COMPLETED,
        report_id=report.id if report is not None else None,
        business_unit=report.business_unit if report is not None else None,
        note=note[:255],
    ))


# ────────────────────────────────────────────────────────────────────────
# Permission
# ────────────────────────────────────────────────────────────────────────


def ensure_may_correct(report: StructuredReport | None, actor_telegram_id: int, is_privileged: bool) -> None:
    """Self-service window, as agreed 2026-08: an employee may correct their own
    entries while the report is still a DRAFT. Once they finalise it, only an
    owner/admin can touch it. Privileged users bypass both checks.
    """
    if is_privileged:
        return
    if report is None:
        raise CorrectionError("Отчёт не найден")
    if report.status != ReportStatus.DRAFT:
        raise CorrectionError(
            "Отчёт уже завершён — исправить может только владелец. "
            "Напишите ему, что нужно поправить."
        )
    if report.submitted_by != actor_telegram_id:
        raise CorrectionError("Это запись другого сотрудника")


# ────────────────────────────────────────────────────────────────────────
# Income
# ────────────────────────────────────────────────────────────────────────


async def _income_label(session: AsyncSession, entry: IncomeEntry) -> str:
    if entry.property_id:
        from db.models import Property
        prop = await session.get(Property, entry.property_id)
        return prop.name_ru if prop else "Проживание"
    if entry.service_item_id:
        from db.models import ServiceItem
        svc = await session.get(ServiceItem, entry.service_item_id)
        return svc.name_ru if svc else "Услуга"
    if entry.minibar_item_id:
        from db.models import MinibarItem, MinibarSection
        item = await session.get(MinibarItem, entry.minibar_item_id)
        if item is None:
            return "Товар"
        shelf = "Мини-шоп" if item.section == MinibarSection.MINISHOP else "Мини-бар"
        return f"{shelf}: {item.name_ru}"
    return "Доход"


async def correct_income_entry(
    session: AsyncSession,
    entry_id: int,
    *,
    actor_telegram_id: int,
    is_privileged: bool = False,
    new_amount: Decimal | None = None,
    new_payment_method: PaymentMethod | None = None,
    delete: bool = False,
    reason: str | None = None,
) -> CorrectionResult:
    """Edit or delete an income entry, keeping the wallet in step."""
    entry = await session.get(IncomeEntry, entry_id)
    if entry is None:
        raise CorrectionError("Запись не найдена")

    report = await session.get(StructuredReport, entry.report_id)
    ensure_may_correct(report, actor_telegram_id, is_privileged)

    old_amount = _q(entry.amount)
    old_pm = entry.payment_method
    label = await _income_label(session, entry)
    wallet_owner = await _wallet_owner_for(session, entry, report)

    if delete:
        new_amount = None
        new_cash = Decimal(0)
    else:
        if new_amount is None:
            new_amount = old_amount
        new_amount = _q(new_amount)
        if new_amount <= 0:
            raise CorrectionError("Сумма должна быть больше нуля — чтобы убрать запись, удалите её")
        if new_payment_method is not None:
            entry.payment_method = new_payment_method
        new_pm = entry.payment_method
        new_cash = new_amount if new_pm == PaymentMethod.CASH else Decimal(0)

    old_cash = old_amount if old_pm == PaymentMethod.CASH else Decimal(0)
    delta = new_cash - old_cash

    suffix = f" · {reason}" if reason else ""
    await _post_adjustment(
        session, telegram_id=wallet_owner, delta=delta, report=report,
        note=(f"Удаление дохода: {label}{suffix}" if delete
              else f"Правка дохода: {label} {old_amount:.0f} → {new_amount:.0f}{suffix}"),
    )

    if report is not None:
        report.total_income = _q(report.total_income) - old_amount + (_q(new_amount) if not delete else Decimal(0))

    if delete:
        # Keep the mirrored calendar prepayment in step, same as reservations.delete_payment.
        from db.models import Prepayment
        prep = (
            await session.execute(select(Prepayment).where(Prepayment.income_entry_id == entry_id))
        ).scalar_one_or_none()
        if prep is not None:
            await session.delete(prep)
        await session.delete(entry)
    else:
        entry.amount = new_amount

    return CorrectionResult(
        entry_id=entry_id, report_id=report.id if report else 0, kind="income",
        label=label, old_amount=old_amount, new_amount=None if delete else new_amount,
        wallet_delta=delta, wallet_owner=wallet_owner,
    )


# ────────────────────────────────────────────────────────────────────────
# Expense
# ────────────────────────────────────────────────────────────────────────


async def correct_expense_entry(
    session: AsyncSession,
    entry_id: int,
    *,
    actor_telegram_id: int,
    is_privileged: bool = False,
    new_amount: Decimal | None = None,
    delete: bool = False,
    reason: str | None = None,
) -> CorrectionResult:
    """Edit or delete an expense entry, keeping the wallet in step.

    Expenses always deduct cash, so the adjustment is the mirror of income:
    lowering an expense gives money back (positive delta).
    """
    entry = await session.get(ExpenseEntry, entry_id)
    if entry is None:
        raise CorrectionError("Запись не найдена")

    report = await session.get(StructuredReport, entry.report_id)
    ensure_may_correct(report, actor_telegram_id, is_privileged)

    old_amount = _q(entry.amount)
    label = entry.description or "Расход"
    wallet_owner = await _wallet_owner_for(session, entry, report)

    if delete:
        new_amount = None
        delta = old_amount            # the whole deduction comes back
    else:
        new_amount = _q(old_amount if new_amount is None else new_amount)
        if new_amount <= 0:
            raise CorrectionError("Сумма должна быть больше нуля — чтобы убрать запись, удалите её")
        delta = old_amount - new_amount   # lower expense → wallet gains

    suffix = f" · {reason}" if reason else ""
    await _post_adjustment(
        session, telegram_id=wallet_owner, delta=delta, report=report,
        note=(f"Удаление расхода: {label}{suffix}" if delete
              else f"Правка расхода: {label} {old_amount:.0f} → {new_amount:.0f}{suffix}"),
    )

    if report is not None:
        report.total_expense = _q(report.total_expense) - old_amount + (_q(new_amount) if not delete else Decimal(0))

    if delete:
        await session.delete(entry)
    else:
        entry.amount = new_amount

    return CorrectionResult(
        entry_id=entry_id, report_id=report.id if report else 0, kind="expense",
        label=label, old_amount=old_amount, new_amount=None if delete else new_amount,
        wallet_delta=delta, wallet_owner=wallet_owner,
    )


# ────────────────────────────────────────────────────────────────────────
# Transfers sent to the wrong wallet
# ────────────────────────────────────────────────────────────────────────


async def reverse_transfer(
    session: AsyncSession,
    tx_id: int,
    *,
    actor_telegram_id: int,
    is_privileged: bool = False,
    reason: str | None = None,
) -> WalletTransaction:
    """Unwind a transfer that was accepted by the wrong person.

    Flipping the status to REVERSED is enough: both balance formulas count
    incoming only when COMPLETED and outgoing only when PENDING/COMPLETED, so
    the money returns to the sender and leaves the receiver in one step, with no
    compensating rows to get out of sync.

    Allowed for the receiver (they accepted it by mistake) and for owner/admin
    (when the receiver is unreachable).
    """
    tx = await session.get(WalletTransaction, tx_id)
    if tx is None:
        raise CorrectionError("Перевод не найден")

    if tx.transaction_type not in (
        WalletTransactionType.TRANSFER_TO_EMPLOYEE,
        WalletTransactionType.TRANSFER_TO_SHAVKAT,
    ):
        raise CorrectionError("Возврату подлежат только переводы между сотрудниками")

    if tx.status == WalletTransactionStatus.REVERSED:
        raise CorrectionError("Этот перевод уже возвращён")
    if tx.status != WalletTransactionStatus.COMPLETED:
        raise CorrectionError("Возврат возможен только для принятого перевода")

    if not is_privileged and tx.receiver_telegram_id != actor_telegram_id:
        raise CorrectionError("Вернуть перевод может получатель или владелец")

    tx.status = WalletTransactionStatus.REVERSED
    stamp = f"Возврат (ошибочный перевод) от {actor_telegram_id}"
    if reason:
        stamp += f": {reason}"
    tx.note = f"{tx.note} · {stamp}" if tx.note else stamp
    tx.note = tx.note[:2000]
    return tx
