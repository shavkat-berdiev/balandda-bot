"""End-to-end check of the correction service against a real (sqlite) DB.

Replays the incident from project_wallet_gaps.md: 1 260 000 typed as 12 600 000.
"""
import asyncio
from decimal import Decimal

from sqlalchemy import select, func, or_, and_
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from db.models import (
    Base, User, StructuredReport, IncomeEntry, ExpenseEntry, WalletTransaction,
)
from db.enums import (
    BusinessUnit, ExpenseCategory, PaymentMethod, ReportStatus, UserRole, Language,
    WalletTransactionStatus, WalletTransactionType,
)
from services.entry_corrections import (
    correct_income_entry, correct_expense_entry, reverse_transfer, CorrectionError,
)

NARGIS, SHAVKAT, OTHER = 111, 222, 333


async def balance(session, tid):
    """Exact copy of bot/handlers/wallet.py::get_wallet_balance."""
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
                WalletTransactionType.TRANSFER_TO_EMPLOYEE, WalletTransactionType.TRANSFER_TO_SHAVKAT,
                WalletTransactionType.CASH_TO_BANK, WalletTransactionType.PURCHASE,
                WalletTransactionType.SALARY, WalletTransactionType.EXPENSE,
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


async def mk_report(session, who=NARGIS, status=ReportStatus.DRAFT):
    from datetime import date
    r = StructuredReport(report_date=date(2026, 8, 4), business_unit=BusinessUnit.RESORT,
                         status=status, submitted_by=who, total_income=0, total_expense=0)
    session.add(r); await session.flush()
    return r


async def add_cash_income(session, report, amount, wallet_owner):
    e = IncomeEntry(report_id=report.id, payment_method=PaymentMethod.CASH,
                    amount=Decimal(amount), quantity=1)
    session.add(e)
    tx = WalletTransaction(sender_telegram_id=wallet_owner, amount=Decimal(amount),
                           transaction_type=WalletTransactionType.CASH_IN,
                           status=WalletTransactionStatus.COMPLETED,
                           report_id=report.id, business_unit=report.business_unit)
    session.add(tx); await session.flush()
    e.wallet_tx_id = tx.id
    report.total_income = Decimal(report.total_income or 0) + Decimal(amount)
    await session.flush()
    return e


def check(name, got, want):
    ok = got == want
    print(f"  {'PASS' if ok else 'FAIL'}  {name}: got {got}, want {want}")
    assert ok, name


async def main():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as c:
        await c.run_sync(Base.metadata.create_all)
    Session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with Session() as s:
        for tid, name in ((NARGIS, "Наргис"), (SHAVKAT, "Шавкат"), (OTHER, "Азизов")):
            s.add(User(telegram_id=tid, full_name=name, role=UserRole.RESORT_MANAGER,
                       language=Language.RU, is_active=True))
        await s.commit()

        # ── 1. The 10× typo, corrected ──────────────────────────────────
        print("\n1. Income typed 10x too high, then corrected")
        rep = await mk_report(s)
        entry = await add_cash_income(s, rep, "12600000", NARGIS)
        await s.commit()
        check("wallet after wrong entry", await balance(s, NARGIS), Decimal("12600000"))

        res = await correct_income_entry(s, entry.id, actor_telegram_id=NARGIS,
                                         new_amount=Decimal("1260000"))
        await s.commit()
        check("adjustment posted", res.wallet_delta, Decimal("-11340000"))
        check("wallet after fix", await balance(s, NARGIS), Decimal("1260000"))
        check("report total", Decimal(str(rep.total_income)), Decimal("1260000"))
        check("entry amount", Decimal(str((await s.get(IncomeEntry, entry.id)).amount)),
              Decimal("1260000"))

        # ── 2. Mini shop: reverses the SELLER's wallet, not the recorder's ──
        print("\n2. Mini shop sale recorded by someone else")
        rep2 = await mk_report(s, who=OTHER)
        ms = await add_cash_income(s, rep2, "300000", NARGIS)   # seller = Наргис
        await s.commit()
        check("seller credited", await balance(s, NARGIS), Decimal("1560000"))
        check("recorder untouched", await balance(s, OTHER), Decimal("0"))

        await correct_income_entry(s, ms.id, actor_telegram_id=OTHER, delete=True)
        await s.commit()
        check("seller debited on delete", await balance(s, NARGIS), Decimal("1260000"))
        check("recorder still untouched", await balance(s, OTHER), Decimal("0"))

        # ── 3. Expense correction is the mirror image ───────────────────
        print("\n3. Expense mistyped high, then corrected")
        exp = ExpenseEntry(report_id=rep.id, expense_category=ExpenseCategory.STAFF,
                           amount=Decimal("5000000"), description="Зарплата")
        s.add(exp)
        etx = WalletTransaction(sender_telegram_id=NARGIS, amount=Decimal("5000000"),
                                transaction_type=WalletTransactionType.EXPENSE,
                                status=WalletTransactionStatus.COMPLETED, report_id=rep.id,
                                business_unit=rep.business_unit)
        s.add(etx); await s.flush()
        exp.wallet_tx_id = etx.id
        rep.total_expense = Decimal("5000000")
        await s.commit()
        check("wallet after expense", await balance(s, NARGIS), Decimal("-3740000"))

        r3 = await correct_expense_entry(s, exp.id, actor_telegram_id=NARGIS,
                                         new_amount=Decimal("500000"))
        await s.commit()
        check("expense adjustment", r3.wallet_delta, Decimal("4500000"))
        check("wallet after expense fix", await balance(s, NARGIS), Decimal("760000"))
        check("report expense total", Decimal(str(rep.total_expense)), Decimal("500000"))

        # ── 4. Transfer accepted by the wrong person, then returned ─────
        print("\n4. Transfer accepted by the wrong person")
        t = WalletTransaction(sender_telegram_id=NARGIS, receiver_telegram_id=OTHER,
                              amount=Decimal("500000"),
                              transaction_type=WalletTransactionType.TRANSFER_TO_EMPLOYEE,
                              status=WalletTransactionStatus.COMPLETED)
        s.add(t); await s.commit()
        check("sender after transfer", await balance(s, NARGIS), Decimal("260000"))
        check("wrong receiver credited", await balance(s, OTHER), Decimal("500000"))

        await reverse_transfer(s, t.id, actor_telegram_id=OTHER)
        await s.commit()
        check("sender got it back", await balance(s, NARGIS), Decimal("760000"))
        check("wrong receiver drained", await balance(s, OTHER), Decimal("0"))

        # ── 5. Guard rails ──────────────────────────────────────────────
        print("\n5. Guard rails")
        try:
            await reverse_transfer(s, t.id, actor_telegram_id=OTHER)
            print("  FAIL  double reversal allowed"); raise SystemExit(1)
        except CorrectionError as e:
            print(f"  PASS  double reversal blocked: {e}")

        # Fresh COMPLETED transfer, so the permission check is what rejects —
        # not the already-reversed status.
        t2 = WalletTransaction(sender_telegram_id=NARGIS, receiver_telegram_id=OTHER,
                               amount=Decimal("70000"),
                               transaction_type=WalletTransactionType.TRANSFER_TO_EMPLOYEE,
                               status=WalletTransactionStatus.COMPLETED)
        s.add(t2); await s.commit()
        try:
            await reverse_transfer(s, t2.id, actor_telegram_id=SHAVKAT)
            print("  FAIL  stranger could reverse"); raise SystemExit(1)
        except CorrectionError as e:
            assert "получатель" in str(e), f"wrong rejection reason: {e}"
            print(f"  PASS  stranger cannot reverse: {e}")
        # ...but the owner can force it
        await reverse_transfer(s, t2.id, actor_telegram_id=SHAVKAT, is_privileged=True)
        await s.commit()
        check("owner force-reverse works", await balance(s, OTHER), Decimal("0"))

        locked = await mk_report(s, who=NARGIS, status=ReportStatus.SUBMITTED)
        le = await add_cash_income(s, locked, "100000", NARGIS)
        await s.commit()
        try:
            await correct_income_entry(s, le.id, actor_telegram_id=NARGIS,
                                       new_amount=Decimal("10000"))
            print("  FAIL  finalised report is editable"); raise SystemExit(1)
        except CorrectionError as e:
            print(f"  PASS  finalised report locked for staff: {e}")

        await s.rollback()
        r5 = await correct_income_entry(s, le.id, actor_telegram_id=SHAVKAT,
                                        is_privileged=True, new_amount=Decimal("10000"))
        await s.commit()
        check("owner may still fix it", r5.wallet_delta, Decimal("-90000"))

        try:
            await correct_income_entry(s, le.id, actor_telegram_id=SHAVKAT,
                                       is_privileged=True, new_amount=Decimal("0"))
            print("  FAIL  zero amount accepted"); raise SystemExit(1)
        except CorrectionError as e:
            print(f"  PASS  zero rejected: {e}")

    print("\nALL CHECKS PASSED")


asyncio.run(main())
