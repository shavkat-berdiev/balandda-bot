"""API endpoints for structured reports and catalog data."""

from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from api.auth import get_current_user
from db.database import get_session
from db.enums import (
    DISCOUNT_REASON_LABELS,
    EXPENSE_CATEGORY_LABELS,
    PAYMENT_METHOD_LABELS,
    PROPERTY_TYPE_LABELS,
    SERVICE_TYPE_LABELS,
)
from db.models import (
    BusinessUnit,
    ExpenseEntry,
    IncomeEntry,
    MinibarItem,
    Property,
    ReportStatus,
    ServiceItem,
    StaffMember,
    StructuredReport,
)

router = APIRouter()


# ── Response schemas ────────────────────────────────────────────────


class PropertyResponse(BaseModel):
    id: int
    code: str
    name_ru: str
    name_uz: str
    property_type: str
    property_type_label: str
    unit_number: str | None
    capacity: int
    has_sauna: bool
    price_weekday: float
    price_weekend: float
    emoji: str
    is_active: bool
    sort_order: int


class ServiceItemResponse(BaseModel):
    id: int
    service_type: str
    service_type_label: str
    name_ru: str
    name_uz: str
    duration_minutes: int
    price: float
    is_active: bool


class MinibarItemResponse(BaseModel):
    id: int
    name_ru: str
    name_uz: str
    price: float
    is_active: bool


class StaffMemberResponse(BaseModel):
    id: int
    name: str
    role_description: str | None
    is_active: bool


class IncomeEntryResponse(BaseModel):
    id: int
    property_name: str | None
    service_name: str | None
    minibar_name: str | None
    payment_method: str
    payment_label: str
    amount: float
    quantity: int
    num_days: int
    discount_type: str | None
    discount_value: float | None
    discount_reason: str | None
    discount_reason_label: str | None
    note: str | None


class ExpenseEntryResponse(BaseModel):
    id: int
    expense_category: str
    category_label: str
    staff_member_name: str | None
    amount: float
    description: str
    note: str | None


class StructuredReportResponse(BaseModel):
    id: int
    report_date: date
    business_unit: str
    status: str
    submitted_by: int
    total_income: float
    total_expense: float
    net: float
    previous_balance: float
    note: str | None
    income_entries: list[IncomeEntryResponse]
    expense_entries: list[ExpenseEntryResponse]


class StructuredReportSummary(BaseModel):
    id: int
    report_date: date
    status: str
    total_income: float
    total_expense: float
    net: float
    income_count: int
    expense_count: int


# ── Catalog endpoints ──────────────────────────────────────────────


@router.get("/properties", response_model=list[PropertyResponse])
async def list_properties(
    active_only: bool = Query(default=True),
    session: AsyncSession = Depends(get_session),
    _user: dict = Depends(get_current_user),
):
    """List all resort properties."""
    query = select(Property).order_by(Property.sort_order)
    if active_only:
        query = query.where(Property.is_active == True)
    result = await session.execute(query)
    properties = result.scalars().all()

    return [
        PropertyResponse(
            id=p.id,
            code=p.code,
            name_ru=p.name_ru,
            name_uz=p.name_uz,
            property_type=p.property_type.value,
            property_type_label=PROPERTY_TYPE_LABELS.get(p.property_type, p.property_type.value),
            unit_number=p.unit_number,
            capacity=p.capacity,
            has_sauna=p.has_sauna,
            price_weekday=float(p.price_weekday),
            price_weekend=float(p.price_weekend),
            emoji=p.emoji or "🏠",
            is_active=p.is_active,
            sort_order=p.sort_order,
        )
        for p in properties
    ]


@router.get("/services", response_model=list[ServiceItemResponse])
async def list_services(
    active_only: bool = Query(default=True),
    session: AsyncSession = Depends(get_session),
    _user: dict = Depends(get_current_user),
):
    """List all service items (massage, SPA, etc.)."""
    query = select(ServiceItem).order_by(ServiceItem.sort_order)
    if active_only:
        query = query.where(ServiceItem.is_active == True)
    result = await session.execute(query)
    services = result.scalars().all()

    return [
        ServiceItemResponse(
            id=s.id,
            service_type=s.service_type.value,
            service_type_label=SERVICE_TYPE_LABELS.get(s.service_type, s.service_type.value),
            name_ru=s.name_ru,
            name_uz=s.name_uz,
            duration_minutes=s.duration_minutes,
            price=float(s.price),
            is_active=s.is_active,
        )
        for s in services
    ]


@router.get("/minibar", response_model=list[MinibarItemResponse])
async def list_minibar(
    active_only: bool = Query(default=True),
    session: AsyncSession = Depends(get_session),
    _user: dict = Depends(get_current_user),
):
    """List all minibar items."""
    query = select(MinibarItem).order_by(MinibarItem.sort_order)
    if active_only:
        query = query.where(MinibarItem.is_active == True)
    result = await session.execute(query)
    items = result.scalars().all()

    return [
        MinibarItemResponse(
            id=i.id,
            name_ru=i.name_ru,
            name_uz=i.name_uz,
            price=float(i.price),
            is_active=i.is_active,
        )
        for i in items
    ]


@router.get("/staff", response_model=list[StaffMemberResponse])
async def list_staff(
    active_only: bool = Query(default=True),
    session: AsyncSession = Depends(get_session),
    _user: dict = Depends(get_current_user),
):
    """List all staff members."""
    query = select(StaffMember)
    if active_only:
        query = query.where(StaffMember.is_active == True)
    result = await session.execute(query)
    staff = result.scalars().all()

    return [
        StaffMemberResponse(
            id=s.id,
            name=s.name,
            role_description=s.role_description,
            is_active=s.is_active,
        )
        for s in staff
    ]


# ── Structured report endpoints ────────────────────────────────────


@router.get("/list", response_model=list[StructuredReportSummary])
async def list_structured_reports(
    business_unit: BusinessUnit = Query(default=BusinessUnit.RESORT),
    limit: int = Query(default=30, le=365),
    session: AsyncSession = Depends(get_session),
    _user: dict = Depends(get_current_user),
):
    """List structured reports with summary info."""
    query = (
        select(StructuredReport)
        .where(StructuredReport.business_unit == business_unit)
        .order_by(StructuredReport.report_date.desc())
        .limit(limit)
        .options(
            selectinload(StructuredReport.income_entries),
            selectinload(StructuredReport.expense_entries),
        )
    )
    result = await session.execute(query)
    reports = result.scalars().all()

    return [
        StructuredReportSummary(
            id=r.id,
            report_date=r.report_date,
            status=r.status.value,
            total_income=float(r.total_income or 0),
            total_expense=float(r.total_expense or 0),
            net=float(r.total_income or 0) - float(r.total_expense or 0),
            income_count=len(r.income_entries),
            expense_count=len(r.expense_entries),
        )
        for r in reports
    ]


@router.get("/detail/{report_id}", response_model=StructuredReportResponse)
async def get_structured_report(
    report_id: int,
    session: AsyncSession = Depends(get_session),
    _user: dict = Depends(get_current_user),
):
    """Get full detail of a structured report."""
    query = (
        select(StructuredReport)
        .where(StructuredReport.id == report_id)
        .options(
            selectinload(StructuredReport.income_entries).selectinload(IncomeEntry.property),
            selectinload(StructuredReport.income_entries).selectinload(IncomeEntry.service_item),
            selectinload(StructuredReport.income_entries).selectinload(IncomeEntry.minibar_item),
            selectinload(StructuredReport.expense_entries).selectinload(ExpenseEntry.staff_member),
        )
    )
    result = await session.execute(query)
    report = result.scalar_one_or_none()

    if not report:
        raise HTTPException(status_code=404, detail="Report not found")

    income_list = []
    for entry in report.income_entries:
        prop_name = entry.property.name_ru if entry.property else None
        svc_name = entry.service_item.name_ru if entry.service_item else None
        mb_name = entry.minibar_item.name_ru if entry.minibar_item else None
        disc_reason_label = None
        if entry.discount_reason:
            disc_reason_label = DISCOUNT_REASON_LABELS.get(entry.discount_reason, entry.discount_reason.value)

        income_list.append(IncomeEntryResponse(
            id=entry.id,
            property_name=prop_name,
            service_name=svc_name,
            minibar_name=mb_name,
            payment_method=entry.payment_method.value,
            payment_label=PAYMENT_METHOD_LABELS.get(entry.payment_method, entry.payment_method.value),
            amount=float(entry.amount),
            quantity=entry.quantity or 1,
            num_days=entry.num_days or 1,
            discount_type=entry.discount_type.value if entry.discount_type else None,
            discount_value=float(entry.discount_value) if entry.discount_value else None,
            discount_reason=entry.discount_reason.value if entry.discount_reason else None,
            discount_reason_label=disc_reason_label,
            note=entry.note,
        ))

    expense_list = []
    for entry in report.expense_entries:
        expense_list.append(ExpenseEntryResponse(
            id=entry.id,
            expense_category=entry.expense_category.value,
            category_label=EXPENSE_CATEGORY_LABELS.get(entry.expense_category, entry.expense_category.value),
            staff_member_name=entry.staff_member.name if entry.staff_member else None,
            amount=float(entry.amount),
            description=entry.description,
            note=entry.note,
        ))

    return StructuredReportResponse(
        id=report.id,
        report_date=report.report_date,
        business_unit=report.business_unit.value,
        status=report.status.value,
        submitted_by=report.submitted_by,
        total_income=float(report.total_income or 0),
        total_expense=float(report.total_expense or 0),
        net=float(report.total_income or 0) - float(report.total_expense or 0),
        previous_balance=float(report.previous_balance or 0),
        note=report.note,
        income_entries=income_list,
        expense_entries=expense_list,
    )


@router.get("/breakdown")
async def structured_breakdown(
    business_unit: BusinessUnit = Query(default=BusinessUnit.RESORT),
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    session: AsyncSession = Depends(get_session),
    _user: dict = Depends(get_current_user),
):
    """Get aggregated breakdown of structured reports for a date range."""
    if end_date is None:
        end_date = date.today()
    if start_date is None:
        start_date = end_date - timedelta(days=30)

    query = (
        select(StructuredReport)
        .where(
            StructuredReport.business_unit == business_unit,
            StructuredReport.report_date >= start_date,
            StructuredReport.report_date <= end_date,
            StructuredReport.status != ReportStatus.DRAFT,
        )
        .options(
            selectinload(StructuredReport.income_entries).selectinload(IncomeEntry.property),
            selectinload(StructuredReport.income_entries).selectinload(IncomeEntry.service_item),
            selectinload(StructuredReport.income_entries).selectinload(IncomeEntry.minibar_item),
            selectinload(StructuredReport.expense_entries),
        )
        .order_by(StructuredReport.report_date)
    )
    result = await session.execute(query)
    reports = result.scalars().all()

    total_income = 0.0
    total_expense = 0.0
    by_property: dict[str, dict] = {}
    by_payment: dict[str, dict] = {}
    by_expense_cat: dict[str, dict] = {}
    daily_data = []

    for report in reports:
        day_inc = float(report.total_income or 0)
        day_exp = float(report.total_expense or 0)
        total_income += day_inc
        total_expense += day_exp

        daily_data.append({
            "date": report.report_date.isoformat(),
            "income": day_inc,
            "expense": day_exp,
            "net": day_inc - day_exp,
        })

        for entry in report.income_entries:
            if entry.property:
                key = entry.property.code
                label = entry.property.name_ru
                if key not in by_property:
                    by_property[key] = {"label": label, "total": 0.0, "count": 0}
                by_property[key]["total"] += float(entry.amount)
                by_property[key]["count"] += 1

            pm_key = entry.payment_method.value
            pm_label = PAYMENT_METHOD_LABELS.get(entry.payment_method, pm_key)
            if pm_key not in by_payment:
                by_payment[pm_key] = {"label": pm_label, "total": 0.0, "count": 0}
            by_payment[pm_key]["total"] += float(entry.amount)
            by_payment[pm_key]["count"] += 1

        for entry in report.expense_entries:
            ec_key = entry.expense_category.value
            ec_label = EXPENSE_CATEGORY_LABELS.get(entry.expense_category, ec_key)
            if ec_key not in by_expense_cat:
                by_expense_cat[ec_key] = {"label": ec_label, "total": 0.0, "count": 0}
            by_expense_cat[ec_key]["total"] += float(entry.amount)
            by_expense_cat[ec_key]["count"] += 1

    def to_list(data: dict) -> list[dict]:
        return sorted(
            [{"key": k, **v} for k, v in data.items()],
            key=lambda x: x["total"],
            reverse=True,
        )

    return {
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "total_income": total_income,
        "total_expense": total_expense,
        "net": total_income - total_expense,
        "by_property": to_list(by_property),
        "by_payment_method": to_list(by_payment),
        "by_expense_category": to_list(by_expense_cat),
        "daily_totals": daily_data,
    }
