"""API endpoints for structured reports and catalog data."""

from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from api.auth import get_current_user, require_owner
from db.database import get_session
from db.enums import (
    DISCOUNT_REASON_LABELS,
    EXPENSE_CATEGORY_LABELS,
    ExpenseCategory,
    PAYMENT_METHOD_LABELS,
    PaymentMethod,
    PROPERTY_TYPE_LABELS,
    SERVICE_TYPE_LABELS,
)
from db.models import (
    BusinessUnit,
    ExpenseEntry,
    IncomeEntry,
    MinibarItem,
    Prepayment,
    PrepaymentStatus,
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
    business_unit: str
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
    business_unit: Optional[str] = Query(default="RESORT"),
    limit: int = Query(default=30, le=365),
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    session: AsyncSession = Depends(get_session),
    _user: dict = Depends(get_current_user),
):
    """List structured reports with summary info. business_unit=ALL for both."""
    query = (
        select(StructuredReport)
        .order_by(StructuredReport.report_date.desc())
        .limit(limit)
        .options(
            selectinload(StructuredReport.income_entries),
            selectinload(StructuredReport.expense_entries),
        )
    )
    if business_unit and business_unit != "ALL":
        try:
            query = query.where(StructuredReport.business_unit == BusinessUnit(business_unit))
        except ValueError:
            pass
    if start_date:
        query = query.where(StructuredReport.report_date >= start_date)
    if end_date:
        query = query.where(StructuredReport.report_date <= end_date)
    result = await session.execute(query)
    reports = result.scalars().all()

    return [
        StructuredReportSummary(
            id=r.id,
            report_date=r.report_date,
            business_unit=r.business_unit.value,
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
    business_unit: Optional[str] = Query(default="RESORT"),
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
    if business_unit and business_unit != "ALL":
        try:
            query = query.where(StructuredReport.business_unit == BusinessUnit(business_unit))
        except ValueError:
            pass

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


@router.get("/transactions")
async def structured_transactions(
    business_unit: Optional[BusinessUnit] = None,
    entry_type: Optional[str] = Query(default=None, description="income or expense"),
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    limit: int = Query(default=100, le=500),
    session: AsyncSession = Depends(get_session),
    _user: dict = Depends(get_current_user),
):
    """Return a flat list of all income/expense entries as transactions."""
    if end_date is None:
        end_date = date.today()
    if start_date is None:
        start_date = end_date - timedelta(days=30)

    query = (
        select(StructuredReport)
        .where(
            StructuredReport.report_date >= start_date,
            StructuredReport.report_date <= end_date,
        )
        .options(
            selectinload(StructuredReport.income_entries).selectinload(IncomeEntry.property),
            selectinload(StructuredReport.income_entries).selectinload(IncomeEntry.service_item),
            selectinload(StructuredReport.income_entries).selectinload(IncomeEntry.minibar_item),
            selectinload(StructuredReport.expense_entries).selectinload(ExpenseEntry.staff_member),
        )
        .order_by(StructuredReport.report_date.desc())
    )
    if business_unit:
        query = query.where(StructuredReport.business_unit == business_unit)

    result = await session.execute(query)
    reports = result.scalars().all()

    transactions = []
    for report in reports:
        bu = report.business_unit.value

        if entry_type != "expense":
            for entry in report.income_entries:
                name = (
                    entry.property.name_ru if entry.property else
                    entry.service_item.name_ru if entry.service_item else
                    entry.minibar_item.name_ru if entry.minibar_item else
                    "Доход"
                )
                category = (
                    "Проживание" if entry.property else
                    "Услуги" if entry.service_item else
                    "Мини-бар" if entry.minibar_item else
                    "Прочее"
                )
                transactions.append({
                    "id": f"inc-{entry.id}",
                    "date": report.report_date.isoformat(),
                    "type": "income",
                    "business_unit": bu,
                    "category": category,
                    "name": name,
                    "payment_method": PAYMENT_METHOD_LABELS.get(
                        entry.payment_method, entry.payment_method.value
                    ),
                    "amount": float(entry.amount),
                    "quantity": entry.quantity or 1,
                    "num_days": entry.num_days or 1,
                    "note": entry.note,
                    "status": report.status.value,
                })

        if entry_type != "income":
            for entry in report.expense_entries:
                transactions.append({
                    "id": f"exp-{entry.id}",
                    "date": report.report_date.isoformat(),
                    "type": "expense",
                    "business_unit": bu,
                    "category": EXPENSE_CATEGORY_LABELS.get(
                        entry.expense_category, entry.expense_category.value
                    ),
                    "name": entry.description or EXPENSE_CATEGORY_LABELS.get(
                        entry.expense_category, entry.expense_category.value
                    ),
                    "payment_method": None,
                    "amount": float(entry.amount),
                    "quantity": 1,
                    "num_days": 1,
                    "note": entry.note,
                    "status": report.status.value,
                })

    # Sort by date desc, then by amount desc
    transactions.sort(key=lambda t: (t["date"], t["amount"]), reverse=True)
    return transactions[:limit]


@router.get("/dashboard")
async def structured_dashboard(
    business_unit: Optional[str] = Query(default="RESORT"),
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    session: AsyncSession = Depends(get_session),
    _user: dict = Depends(get_current_user),
):
    """Dashboard data: totals, income breakdown, expense breakdown, daily trend, service breakdown, prepayments."""
    if end_date is None:
        end_date = date.today()
    if start_date is None:
        start_date = end_date

    query = (
        select(StructuredReport)
        .where(
            StructuredReport.report_date >= start_date,
            StructuredReport.report_date <= end_date,
        )
        .options(
            selectinload(StructuredReport.income_entries).selectinload(IncomeEntry.property),
            selectinload(StructuredReport.income_entries).selectinload(IncomeEntry.service_item),
            selectinload(StructuredReport.income_entries).selectinload(IncomeEntry.minibar_item),
            selectinload(StructuredReport.expense_entries),
        )
        .order_by(StructuredReport.report_date)
    )
    if business_unit and business_unit != "ALL":
        try:
            query = query.where(StructuredReport.business_unit == BusinessUnit(business_unit))
        except ValueError:
            pass

    result = await session.execute(query)
    reports = result.scalars().all()

    total_income = 0.0
    total_expense = 0.0
    report_count = 0

    by_income_cat: dict[str, float] = {}
    by_expense_cat: dict[str, float] = {}
    by_payment: dict[str, float] = {}
    by_property: dict[str, float] = {}
    by_service: dict[str, float] = {}
    daily_data: dict[str, dict] = {}

    for report in reports:
        day_inc = float(report.total_income or 0)
        day_exp = float(report.total_expense or 0)
        total_income += day_inc
        total_expense += day_exp
        report_count += 1

        day_key = report.report_date.isoformat()
        if day_key not in daily_data:
            daily_data[day_key] = {"date": day_key, "income": 0, "expense": 0}
        daily_data[day_key]["income"] += day_inc
        daily_data[day_key]["expense"] += day_exp

        for entry in report.income_entries:
            amt = float(entry.amount)

            # By income category
            if entry.property:
                cat = "Проживание"
                prop_name = entry.property.name_ru
                by_property[prop_name] = by_property.get(prop_name, 0) + amt
            elif entry.service_item:
                cat = "Услуги"
                svc_name = entry.service_item.name_ru
                by_service[svc_name] = by_service.get(svc_name, 0) + amt
            elif entry.minibar_item:
                cat = "Мини-бар"
            else:
                cat = "Прочее"
            by_income_cat[cat] = by_income_cat.get(cat, 0) + amt

            # By payment method
            pm_label = PAYMENT_METHOD_LABELS.get(entry.payment_method, entry.payment_method.value)
            by_payment[pm_label] = by_payment.get(pm_label, 0) + amt

        for entry in report.expense_entries:
            ec_label = EXPENSE_CATEGORY_LABELS.get(entry.expense_category, entry.expense_category.value)
            by_expense_cat[ec_label] = by_expense_cat.get(ec_label, 0) + float(entry.amount)

    def dict_to_chart(d: dict) -> list:
        return sorted(
            [{"name": k, "value": v} for k, v in d.items()],
            key=lambda x: x["value"],
            reverse=True,
        )

    # ── Prepayment stats ──
    prep_query = select(Prepayment).where(
        Prepayment.check_in_date >= start_date,
        Prepayment.check_in_date <= end_date,
    )
    prep_result = await session.execute(prep_query)
    prepayments = prep_result.scalars().all()

    prep_total = float(sum(p.amount for p in prepayments))
    prep_confirmed = float(sum(p.amount for p in prepayments if p.status == PrepaymentStatus.CONFIRMED))
    prep_pending = float(sum(p.amount for p in prepayments if p.status == PrepaymentStatus.PENDING))
    prep_count = len(prepayments)

    return {
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "total_income": total_income,
        "total_expense": total_expense,
        "net": total_income - total_expense,
        "report_count": report_count,
        "income_by_category": dict_to_chart(by_income_cat),
        "expense_by_category": dict_to_chart(by_expense_cat),
        "by_payment_method": dict_to_chart(by_payment),
        "by_property": dict_to_chart(by_property),
        "by_service": dict_to_chart(by_service),
        "daily_totals": sorted(daily_data.values(), key=lambda x: x["date"]),
        "prepayments": {
            "total": prep_total,
            "confirmed": prep_confirmed,
            "pending": prep_pending,
            "count": prep_count,
        },
    }


# ── Report editing endpoints (owner only) ─────────────────────────


class ReportUpdateRequest(BaseModel):
    report_date: Optional[date] = None
    business_unit: Optional[str] = None
    note: Optional[str] = None


class IncomeEntryUpdateRequest(BaseModel):
    amount: Optional[float] = None
    payment_method: Optional[str] = None
    quantity: Optional[int] = None
    num_days: Optional[int] = None
    note: Optional[str] = None


class ExpenseEntryUpdateRequest(BaseModel):
    amount: Optional[float] = None
    expense_category: Optional[str] = None
    description: Optional[str] = None
    note: Optional[str] = None


@router.put("/report/{report_id}")
async def update_report(
    report_id: int,
    body: ReportUpdateRequest,
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Edit report metadata (date, business unit, note). Owner only."""
    require_owner(user)

    result = await session.execute(
        select(StructuredReport).where(StructuredReport.id == report_id)
    )
    report = result.scalar_one_or_none()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")

    if body.report_date is not None:
        report.report_date = body.report_date
    if body.business_unit is not None:
        try:
            report.business_unit = BusinessUnit(body.business_unit)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid business_unit: {body.business_unit}")
    if body.note is not None:
        report.note = body.note

    await session.commit()
    return {"ok": True, "id": report.id}


@router.put("/income-entry/{entry_id}")
async def update_income_entry(
    entry_id: int,
    body: IncomeEntryUpdateRequest,
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Edit an income entry. Owner only. Recalculates report total."""
    require_owner(user)

    result = await session.execute(
        select(IncomeEntry).where(IncomeEntry.id == entry_id)
    )
    entry = result.scalar_one_or_none()
    if not entry:
        raise HTTPException(status_code=404, detail="Income entry not found")

    old_amount = float(entry.amount)

    if body.amount is not None:
        entry.amount = body.amount
    if body.payment_method is not None:
        try:
            entry.payment_method = PaymentMethod(body.payment_method)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid payment_method: {body.payment_method}")
    if body.quantity is not None:
        entry.quantity = body.quantity
    if body.num_days is not None:
        entry.num_days = body.num_days
    if body.note is not None:
        entry.note = body.note

    # Recalculate report total
    new_amount = float(entry.amount)
    report = await session.get(StructuredReport, entry.report_id)
    if report:
        report.total_income = float(report.total_income or 0) - old_amount + new_amount

    await session.commit()
    return {"ok": True, "id": entry.id, "report_id": entry.report_id}


@router.put("/expense-entry/{entry_id}")
async def update_expense_entry(
    entry_id: int,
    body: ExpenseEntryUpdateRequest,
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Edit an expense entry. Owner only. Recalculates report total."""
    require_owner(user)

    result = await session.execute(
        select(ExpenseEntry).where(ExpenseEntry.id == entry_id)
    )
    entry = result.scalar_one_or_none()
    if not entry:
        raise HTTPException(status_code=404, detail="Expense entry not found")

    old_amount = float(entry.amount)

    if body.amount is not None:
        entry.amount = body.amount
    if body.expense_category is not None:
        try:
            entry.expense_category = ExpenseCategory(body.expense_category)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid expense_category: {body.expense_category}")
    if body.description is not None:
        entry.description = body.description
    if body.note is not None:
        entry.note = body.note

    # Recalculate report total
    new_amount = float(entry.amount)
    report = await session.get(StructuredReport, entry.report_id)
    if report:
        report.total_expense = float(report.total_expense or 0) - old_amount + new_amount

    await session.commit()
    return {"ok": True, "id": entry.id, "report_id": entry.report_id}


@router.delete("/income-entry/{entry_id}")
async def delete_income_entry(
    entry_id: int,
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Delete an income entry. Owner only. Recalculates report total."""
    require_owner(user)

    result = await session.execute(
        select(IncomeEntry).where(IncomeEntry.id == entry_id)
    )
    entry = result.scalar_one_or_none()
    if not entry:
        raise HTTPException(status_code=404, detail="Income entry not found")

    # Update report total
    report = await session.get(StructuredReport, entry.report_id)
    if report:
        report.total_income = float(report.total_income or 0) - float(entry.amount)

    await session.delete(entry)
    await session.commit()
    return {"ok": True, "report_id": report.id if report else None}


@router.delete("/expense-entry/{entry_id}")
async def delete_expense_entry(
    entry_id: int,
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Delete an expense entry. Owner only. Recalculates report total."""
    require_owner(user)

    result = await session.execute(
        select(ExpenseEntry).where(ExpenseEntry.id == entry_id)
    )
    entry = result.scalar_one_or_none()
    if not entry:
        raise HTTPException(status_code=404, detail="Expense entry not found")

    # Update report total
    report = await session.get(StructuredReport, entry.report_id)
    if report:
        report.total_expense = float(report.total_expense or 0) - float(entry.amount)

    await session.delete(entry)
    await session.commit()
    return {"ok": True, "report_id": report.id if report else None}
