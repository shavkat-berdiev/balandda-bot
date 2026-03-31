"""API endpoints for imported daily reports with detailed breakdowns."""

from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from api.auth import get_current_user
from db.database import get_session
from db.models import (
    AccommodationType,
    ACCOMMODATION_TYPE_LABELS,
    BusinessUnit,
    DailyReport,
    EXPENSE_CATEGORY_LABELS,
    ExpenseCategory,
    PAYMENT_METHOD_LABELS,
    PaymentMethod,
    ReportExpense,
    ReportLineItem,
)

router = APIRouter()


# ── Response schemas ────────────────────────────────────────────────

class LineItemResponse(BaseModel):
    id: int
    accommodation_type: str
    accommodation_label: str
    unit_number: str | None
    unit_label: str
    service_description: str | None
    payment_method: str
    payment_label: str
    amount: float
    discount_percent: int | None
    discount_reason: str | None
    note: str | None


class ExpenseResponse(BaseModel):
    id: int
    expense_category: str
    category_label: str
    description: str
    amount: float


class DailyReportResponse(BaseModel):
    id: int
    report_date: date
    business_unit: str
    total_income: float
    total_expense: float
    net: float
    balance: float
    previous_balance: float
    line_items: list[LineItemResponse]
    expenses: list[ExpenseResponse]


class DailyReportSummary(BaseModel):
    id: int
    report_date: date
    total_income: float
    total_expense: float
    net: float
    units_count: int
    expenses_count: int


class BreakdownItem(BaseModel):
    label: str
    key: str
    total: float
    count: int


class PeriodBreakdown(BaseModel):
    start_date: date
    end_date: date
    total_income: float
    total_expense: float
    net: float
    by_accommodation: list[BreakdownItem]
    by_payment_method: list[BreakdownItem]
    by_expense_category: list[BreakdownItem]
    daily_totals: list[dict]


# ── Endpoints ───────────────────────────────────────────────────────

@router.get("/list", response_model=list[DailyReportSummary])
async def list_reports(
    business_unit: BusinessUnit = Query(default=BusinessUnit.RESORT),
    limit: int = Query(default=30, le=365),
    session: AsyncSession = Depends(get_session),
    _user: dict = Depends(get_current_user),
):
    """List daily reports with summary info."""
    query = (
        select(DailyReport)
        .where(DailyReport.business_unit == business_unit)
        .order_by(DailyReport.report_date.desc())
        .limit(limit)
        .options(selectinload(DailyReport.line_items), selectinload(DailyReport.expenses))
    )
    result = await session.execute(query)
    reports = result.scalars().all()

    return [
        DailyReportSummary(
            id=r.id,
            report_date=r.report_date,
            total_income=float(r.total_income),
            total_expense=float(r.total_expense),
            net=float(r.total_income) - float(r.total_expense),
            units_count=len(set(li.unit_label for li in r.line_items)),
            expenses_count=len(r.expenses),
        )
        for r in reports
    ]


@router.get("/detail/{report_id}", response_model=DailyReportResponse)
async def get_report_detail(
    report_id: int,
    session: AsyncSession = Depends(get_session),
    _user: dict = Depends(get_current_user),
):
    """Get full detail of a daily report."""
    query = (
        select(DailyReport)
        .where(DailyReport.id == report_id)
        .options(selectinload(DailyReport.line_items), selectinload(DailyReport.expenses))
    )
    result = await session.execute(query)
    report = result.scalar_one_or_none()

    if not report:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Report not found")

    return DailyReportResponse(
        id=report.id,
        report_date=report.report_date,
        business_unit=report.business_unit.value,
        total_income=float(report.total_income),
        total_expense=float(report.total_expense),
        net=float(report.total_income) - float(report.total_expense),
        balance=float(report.balance),
        previous_balance=float(report.previous_balance),
        line_items=[
            LineItemResponse(
                id=li.id,
                accommodation_type=li.accommodation_type.value,
                accommodation_label=ACCOMMODATION_TYPE_LABELS.get(li.accommodation_type, li.accommodation_type.value),
                unit_number=li.unit_number,
                unit_label=li.unit_label,
                service_description=li.service_description,
                payment_method=li.payment_method.value,
                payment_label=PAYMENT_METHOD_LABELS.get(li.payment_method, li.payment_method.value),
                amount=float(li.amount),
                discount_percent=li.discount_percent,
                discount_reason=li.discount_reason,
                note=li.note,
            )
            for li in report.line_items
        ],
        expenses=[
            ExpenseResponse(
                id=e.id,
                expense_category=e.expense_category.value,
                category_label=EXPENSE_CATEGORY_LABELS.get(e.expense_category, e.expense_category.value),
                description=e.description,
                amount=float(e.amount),
            )
            for e in report.expenses
        ],
    )


@router.get("/breakdown", response_model=PeriodBreakdown)
async def period_breakdown(
    business_unit: BusinessUnit = Query(default=BusinessUnit.RESORT),
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    session: AsyncSession = Depends(get_session),
    _user: dict = Depends(get_current_user),
):
    """Get aggregated breakdown for a date range."""
    if end_date is None:
        end_date = date.today()
    if start_date is None:
        start_date = end_date - timedelta(days=30)

    # Get reports in range
    query = (
        select(DailyReport)
        .where(
            DailyReport.business_unit == business_unit,
            DailyReport.report_date >= start_date,
            DailyReport.report_date <= end_date,
        )
        .options(selectinload(DailyReport.line_items), selectinload(DailyReport.expenses))
        .order_by(DailyReport.report_date)
    )
    result = await session.execute(query)
    reports = result.scalars().all()

    # Aggregate by accommodation type
    acc_totals: dict[str, dict] = {}
    payment_totals: dict[str, dict] = {}
    expense_totals: dict[str, dict] = {}
    daily_data: list[dict] = []
    total_income = 0.0
    total_expense = 0.0

    for report in reports:
        day_income = float(report.total_income)
        day_expense = float(report.total_expense)
        total_income += day_income
        total_expense += day_expense

        daily_data.append({
            "date": report.report_date.isoformat(),
            "income": day_income,
            "expense": day_expense,
            "net": day_income - day_expense,
        })

        for li in report.line_items:
            acc_key = li.accommodation_type.value
            acc_label = ACCOMMODATION_TYPE_LABELS.get(li.accommodation_type, acc_key)
            if acc_key not in acc_totals:
                acc_totals[acc_key] = {"label": acc_label, "total": 0.0, "count": 0}
            acc_totals[acc_key]["total"] += float(li.amount)
            acc_totals[acc_key]["count"] += 1

            pm_key = li.payment_method.value
            pm_label = PAYMENT_METHOD_LABELS.get(li.payment_method, pm_key)
            if pm_key not in payment_totals:
                payment_totals[pm_key] = {"label": pm_label, "total": 0.0, "count": 0}
            payment_totals[pm_key]["total"] += float(li.amount)
            payment_totals[pm_key]["count"] += 1

        for exp in report.expenses:
            ec_key = exp.expense_category.value
            ec_label = EXPENSE_CATEGORY_LABELS.get(exp.expense_category, ec_key)
            if ec_key not in expense_totals:
                expense_totals[ec_key] = {"label": ec_label, "total": 0.0, "count": 0}
            expense_totals[ec_key]["total"] += float(exp.amount)
            expense_totals[ec_key]["count"] += 1

    def to_breakdown_list(data: dict) -> list[BreakdownItem]:
        return sorted(
            [BreakdownItem(key=k, **v) for k, v in data.items()],
            key=lambda x: x.total,
            reverse=True,
        )

    return PeriodBreakdown(
        start_date=start_date,
        end_date=end_date,
        total_income=total_income,
        total_expense=total_expense,
        net=total_income - total_expense,
        by_accommodation=to_breakdown_list(acc_totals),
        by_payment_method=to_breakdown_list(payment_totals),
        by_expense_category=to_breakdown_list(expense_totals),
        daily_totals=daily_data,
    )
