"""Shared SPA payment recording — used by the API (Расписание SPA) and the SPA bot.

Same flow as accommodation payments from the calendar: the payment lands as an
IncomeEntry in today's DRAFT RESORT report (service_item_id set → shows in the
SPA section of analytics), cash also tops up the operator's wallet.
"""

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import (
    BusinessUnit,
    IncomeEntry,
    PaymentMethod,
    ReportStatus,
    SpaAppointment,
    StructuredReport,
    WalletTransaction,
    WalletTransactionStatus,
    WalletTransactionType,
)

TASHKENT = timezone(timedelta(hours=5))


async def get_or_create_report(session: AsyncSession, operator: int) -> StructuredReport:
    """Today's draft RESORT report for this operator (SPA revenue lands in the
    SPA/services section of analytics via service_item_id)."""
    today = datetime.now(TASHKENT).date()
    report = (
        await session.execute(
            select(StructuredReport).where(
                StructuredReport.submitted_by == operator,
                StructuredReport.report_date == today,
                StructuredReport.business_unit == BusinessUnit.RESORT,
                StructuredReport.status == ReportStatus.DRAFT,
            ).order_by(StructuredReport.id)
        )
    ).scalars().first()
    if not report:
        report = StructuredReport(
            report_date=today, business_unit=BusinessUnit.RESORT,
            status=ReportStatus.DRAFT, submitted_by=operator,
        )
        session.add(report)
        await session.flush()
    return report


async def record_spa_payment(session: AsyncSession, appt: SpaAppointment,
                             amount: float, pm: PaymentMethod, operator: int,
                             report: StructuredReport | None = None) -> IncomeEntry:
    """Record a guest payment for an appointment. Caller commits.
    Income entry carries service_item_id → revenue shows in SPA analytics.

    Cash always credits `operator`'s wallet — the person actually taking the money.
    Pass `report` when the caller already has one (the bot report flow lets the
    operator pick a date); otherwise today's draft RESORT report is used.
    """
    report = report or await get_or_create_report(session, operator)
    amt = round(float(amount))
    income = IncomeEntry(
        report_id=report.id,
        service_item_id=appt.service_id,
        spa_appointment_id=appt.id,
        reservation_id=appt.reservation_id,
        payment_method=pm,
        amount=amt,
        note=f"SPA запись #{appt.id}",
    )
    session.add(income)
    report.total_income = (report.total_income or 0) + amt
    if pm == PaymentMethod.CASH:
        session.add(WalletTransaction(
            sender_telegram_id=operator, amount=amt,
            transaction_type=WalletTransactionType.CASH_IN,
            status=WalletTransactionStatus.COMPLETED,
            report_id=report.id, business_unit=BusinessUnit.RESORT,
        ))
    await session.flush()
    return income


