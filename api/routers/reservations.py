"""Admin reservations + calendar API.

Backs the availability calendar in the dashboard: list bookings/blocks for a date
range, create a booking or manual block (double-booking is rejected by the DB
exclusion constraint -> 409), update, and cancel.
"""

from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth import get_current_user
from db.database import get_session
from db.enums import (
    BusinessUnit,
    PAYMENT_METHOD_LABELS,
    PaymentMethod,
    PrepaymentStatus,
    RESERVATION_SOURCE_LABELS,
    RESERVATION_STATUS_LABELS,
    ReportStatus,
    ReservationSource,
    ReservationStatus,
    WalletTransactionStatus,
    WalletTransactionType,
)
from db.models import (
    IncomeEntry, Prepayment, Property, Reservation, ReservationEvent,
    StructuredReport, User, WalletTransaction,
)

router = APIRouter()


class ReservationCreate(BaseModel):
    property_id: int
    check_in: date
    check_out: date
    guest_name: str | None = None
    guest_phone: str | None = None
    guest_count: int | None = None
    status: str = "CONFIRMED"          # use "BLOCKED" for maintenance/owner holds
    source: str = "MANUAL"
    total_amount: float | None = None
    deposit_amount: float | None = None
    note: str | None = None


class PaymentInput(BaseModel):
    amount: float
    payment_method: str


class ReservationUpdate(BaseModel):
    check_in: date | None = None
    check_out: date | None = None
    guest_name: str | None = None
    guest_phone: str | None = None
    guest_count: int | None = None
    status: str | None = None
    total_amount: float | None = None
    deposit_amount: float | None = None
    note: str | None = None


def _stay_price(prop, ci, co):
    """Estimate the full stay price from the unit's catalog rate (Sat = weekend)."""
    if not prop or not ci or not co or co <= ci:
        return None
    total = 0.0
    d = ci
    while d < co:
        total += float(prop.price_weekend if d.weekday() == 5 else prop.price_weekday)
        d += timedelta(days=1)
    return round(total)


def _out(r: Reservation, property_name: str | None = None, income_paid: float = 0.0,
         total_override: float | None = None) -> dict:
    st = r.status if isinstance(r.status, ReservationStatus) else ReservationStatus(r.status)
    sr = r.source if isinstance(r.source, ReservationSource) else ReservationSource(r.source)
    deposit = float(r.deposit_amount) if r.deposit_amount is not None else 0.0
    paid = deposit + float(income_paid or 0)
    total = total_override if total_override is not None else (float(r.total_amount) if r.total_amount is not None else None)
    return {
        "id": r.id,
        "property_id": r.property_id,
        "property_name": property_name,
        "guest_name": r.guest_name,
        "guest_phone": r.guest_phone,
        "guest_count": r.guest_count,
        "check_in": r.check_in.isoformat(),
        "check_out": r.check_out.isoformat(),
        "status": st.value,
        "status_label": RESERVATION_STATUS_LABELS.get(st, st.value),
        "source": sr.value,
        "source_label": RESERVATION_SOURCE_LABELS.get(sr, sr.value),
        "total_amount": total,
        "deposit_amount": float(r.deposit_amount) if r.deposit_amount is not None else None,
        "paid_amount": paid,
        "balance": (total - paid) if total is not None else None,
        "note": r.note,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }


def _parse_status(value: str) -> ReservationStatus:
    try:
        return ReservationStatus(value)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"invalid status: {value}")


# ---- change-log helpers ----
_FIELDS = ["check_in", "check_out", "guest_name", "guest_phone",
           "guest_count", "total_amount", "deposit_amount", "note", "status"]
_FIELD_LABELS = {
    "check_in": "Заезд", "check_out": "Выезд", "guest_name": "Имя",
    "guest_phone": "Телефон", "guest_count": "Гостей",
    "total_amount": "Сумма", "deposit_amount": "Предоплата",
    "note": "Заметка", "status": "Статус",
}


def _fmt(field, v):
    if v is None or v == "":
        return "—"
    if field in ("total_amount", "deposit_amount"):
        try:
            return f"{int(round(float(v))):,}".replace(",", " ")
        except (TypeError, ValueError):
            return str(v)
    if field == "status":
        st = v if isinstance(v, ReservationStatus) else ReservationStatus(v)
        return RESERVATION_STATUS_LABELS.get(st, st.value)
    if hasattr(v, "isoformat"):
        return v.isoformat()
    return str(v)


def _diff_text(old: dict, new: dict) -> str:
    parts = []
    for f in _FIELDS:
        ov, nv = _fmt(f, old.get(f)), _fmt(f, new.get(f))
        if ov != nv:
            parts.append(f"{_FIELD_LABELS.get(f, f)}: {ov} → {nv}")
    return "; ".join(parts)


async def _log(session: AsyncSession, reservation_id: int, actor: dict, action: str, detail: str | None = None):
    actor_id = actor.get("telegram_id") if actor else None
    name = None
    if actor_id:
        name = (
            await session.execute(select(User.full_name).where(User.telegram_id == actor_id))
        ).scalar_one_or_none()
    session.add(ReservationEvent(
        reservation_id=reservation_id, actor_id=actor_id, actor_name=name, action=action, detail=detail,
    ))
    await session.commit()


@router.get("")
async def list_reservations(
    from_: date = Query(..., alias="from"),
    to: date = Query(...),
    session: AsyncSession = Depends(get_session),
    user: dict = Depends(get_current_user),
):
    """Reservations/blocks overlapping [from, to), with unit names — for the calendar."""
    rows = (
        await session.execute(
            select(Reservation, Property)
            .join(Property, Property.id == Reservation.property_id)
            .where(Reservation.check_in < to)
            .where(Reservation.check_out > from_)
            .order_by(Reservation.property_id, Reservation.check_in)
        )
    ).all()
    res_ids = [r.id for (r, _p) in rows]
    income_by_res: dict[int, float] = {}
    if res_ids:
        sums = (
            await session.execute(
                select(IncomeEntry.reservation_id, func.coalesce(func.sum(IncomeEntry.amount), 0))
                .where(IncomeEntry.reservation_id.in_(res_ids))
                .group_by(IncomeEntry.reservation_id)
            )
        ).all()
        income_by_res = {rid: float(s) for (rid, s) in sums}
    return [
        _out(r, prop.name_ru, income_by_res.get(r.id, 0.0),
             float(r.total_amount) if r.total_amount is not None else _stay_price(prop, r.check_in, r.check_out))
        for (r, prop) in rows
    ]


@router.post("")
async def create_reservation(
    data: ReservationCreate,
    session: AsyncSession = Depends(get_session),
    user: dict = Depends(get_current_user),
):
    if data.check_out <= data.check_in:
        raise HTTPException(status_code=400, detail="check_out must be after check_in")
    status = _parse_status(data.status)
    try:
        source = ReservationSource(data.source)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"invalid source: {data.source}")

    res = Reservation(
        property_id=data.property_id,
        check_in=data.check_in,
        check_out=data.check_out,
        guest_name=data.guest_name,
        guest_phone=data.guest_phone,
        guest_count=data.guest_count,
        status=status,
        source=source,
        total_amount=data.total_amount,
        deposit_amount=data.deposit_amount,
        note=data.note,
        created_by=user.get("telegram_id"),
    )
    session.add(res)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(status_code=409, detail="Unit is not available for these dates")
    await session.refresh(res)
    await _log(session, res.id, user, "created",
               f"{data.guest_name or RESERVATION_SOURCE_LABELS.get(source, source.value)} · {data.check_in}→{data.check_out}")
    return _out(res)


@router.patch("/{res_id}")
async def update_reservation(
    res_id: int,
    data: ReservationUpdate,
    session: AsyncSession = Depends(get_session),
    user: dict = Depends(get_current_user),
):
    res = await session.get(Reservation, res_id)
    if not res:
        raise HTTPException(status_code=404, detail="not found")
    old = {f: getattr(res, f) for f in _FIELDS}
    if data.status is not None:
        res.status = _parse_status(data.status)
    for field in ("check_in", "check_out", "guest_name", "guest_phone",
                  "guest_count", "total_amount", "deposit_amount", "note"):
        val = getattr(data, field)
        if val is not None:
            setattr(res, field, val)
    if res.check_out <= res.check_in:
        raise HTTPException(status_code=400, detail="check_out must be after check_in")
    new = {f: getattr(res, f) for f in _FIELDS}
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(status_code=409, detail="Unit is not available for these dates")
    detail = _diff_text(old, new)
    if detail:
        await _log(session, res_id, user, "updated", detail)
    await session.refresh(res)
    return _out(res)


@router.post("/{res_id}/cancel")
async def cancel_reservation(
    res_id: int,
    session: AsyncSession = Depends(get_session),
    user: dict = Depends(get_current_user),
):
    res = await session.get(Reservation, res_id)
    if not res:
        raise HTTPException(status_code=404, detail="not found")
    res.status = ReservationStatus.CANCELLED
    await session.commit()
    await _log(session, res_id, user, "cancelled", "Бронь отменена")
    await session.refresh(res)
    return _out(res)


@router.post("/{res_id}/payment")
async def accept_payment(
    res_id: int,
    data: PaymentInput,
    session: AsyncSession = Depends(get_session),
    user: dict = Depends(get_current_user),
):
    """Record a full/balance accommodation payment from the calendar. Creates a
    linked income entry in today's RESORT report (so it lands in analytics) and
    updates the booking's paid total + change log."""
    res = await session.get(Reservation, res_id)
    if not res:
        raise HTTPException(status_code=404, detail="not found")
    if data.amount is None or data.amount <= 0:
        raise HTTPException(status_code=400, detail="amount must be positive")
    try:
        pm = PaymentMethod(data.payment_method)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"invalid payment_method: {data.payment_method}")

    operator = user.get("telegram_id")
    today = datetime.now(timezone(timedelta(hours=5))).date()  # Asia/Tashkent

    report = (
        await session.execute(
            select(StructuredReport).where(
                StructuredReport.submitted_by == operator,
                StructuredReport.report_date == today,
                StructuredReport.business_unit == BusinessUnit.RESORT,
                StructuredReport.status == ReportStatus.DRAFT,
            )
        )
    ).scalar_one_or_none()
    if not report:
        report = StructuredReport(
            report_date=today, business_unit=BusinessUnit.RESORT,
            status=ReportStatus.DRAFT, submitted_by=operator,
        )
        session.add(report)
        await session.flush()

    amt = round(float(data.amount))
    nights = (res.check_out - res.check_in).days or 1
    session.add(IncomeEntry(
        report_id=report.id, property_id=res.property_id, reservation_id=res.id,
        payment_method=pm, amount=amt, num_days=nights,
    ))
    report.total_income = (report.total_income or 0) + amt
    if pm == PaymentMethod.CASH:
        session.add(WalletTransaction(
            sender_telegram_id=operator, amount=amt,
            transaction_type=WalletTransactionType.CASH_IN,
            status=WalletTransactionStatus.COMPLETED,
            report_id=report.id, business_unit=BusinessUnit.RESORT,
        ))
    name = (
        await session.execute(select(User.full_name).where(User.telegram_id == operator))
    ).scalar_one_or_none()
    session.add(ReservationEvent(
        reservation_id=res.id, actor_id=operator, actor_name=name, action="payment",
        detail=f"Оплата проживания: +{amt} сум ({PAYMENT_METHOD_LABELS.get(pm, pm.value)}) · отчёт #{report.id}",
    ))
    await session.commit()

    income = (
        await session.execute(
            select(func.coalesce(func.sum(IncomeEntry.amount), 0)).where(IncomeEntry.reservation_id == res.id)
        )
    ).scalar() or 0
    prop = await session.get(Property, res.property_id)
    total = float(res.total_amount) if res.total_amount is not None else _stay_price(prop, res.check_in, res.check_out)
    return _out(res, prop.name_ru if prop else None, float(income), total)


@router.get("/{res_id}/events")
async def reservation_events(
    res_id: int,
    session: AsyncSession = Depends(get_session),
    user: dict = Depends(get_current_user),
):
    """Change log for a reservation, newest first."""
    rows = (
        await session.execute(
            select(ReservationEvent)
            .where(ReservationEvent.reservation_id == res_id)
            .order_by(ReservationEvent.created_at.desc())
        )
    ).scalars().all()
    return [
        {
            "id": e.id, "action": e.action, "actor_name": e.actor_name,
            "detail": e.detail,
            "created_at": e.created_at.isoformat() if e.created_at else None,
        }
        for e in rows
    ]


@router.post("/import-prepayments")
async def import_prepayments(
    session: AsyncSession = Depends(get_session),
    user: dict = Depends(get_current_user),
):
    """Backfill the calendar from existing prepayments in analytics — the source of
    current bookings until Exely sync exists. Idempotent: a prepayment already linked
    to a reservation is skipped; date overlaps are skipped (and counted)."""
    rows = (
        await session.execute(
            select(Prepayment).where(Prepayment.status != PrepaymentStatus.CANCELLED)
        )
    ).scalars().all()
    # Snapshot fields before any write — a rollback below would expire these ORM
    # objects, and a later attribute access would raise MissingGreenlet.
    snap = [
        {
            "id": p.id, "property_id": p.property_id, "guest_name": p.guest_name,
            "check_in": p.check_in_date, "check_out": p.check_out_date,
            "amount": p.amount, "status": p.status,
        }
        for p in rows
    ]
    linked = set(
        (
            await session.execute(
                select(Reservation.prepayment_id).where(Reservation.prepayment_id.is_not(None))
            )
        ).scalars().all()
    )
    operator = user.get("telegram_id")
    created, skipped = 0, 0
    for s in snap:
        if s["id"] in linked:
            continue
        if not s["check_in"] or not s["check_out"] or s["check_out"] <= s["check_in"]:
            skipped += 1
            continue
        status = (
            ReservationStatus.CONFIRMED
            if s["status"] in (PrepaymentStatus.CONFIRMED, PrepaymentStatus.SETTLED)
            else ReservationStatus.HOLD
        )
        res = Reservation(
            property_id=s["property_id"],
            check_in=s["check_in"],
            check_out=s["check_out"],
            guest_name=s["guest_name"],
            status=status,
            source=ReservationSource.MANUAL,
            deposit_amount=s["amount"],
            prepayment_id=s["id"],
            note="Импорт из предоплат",
            created_by=operator,
        )
        session.add(res)
        try:
            await session.commit()
            created += 1
        except IntegrityError:
            await session.rollback()
            skipped += 1

    # Backfill: link historical accommodation income (recorded before this feature)
    # to bookings by unit + the report's date.
    inc_rows = (
        await session.execute(
            select(IncomeEntry.id, IncomeEntry.property_id, StructuredReport.report_date)
            .join(StructuredReport, StructuredReport.id == IncomeEntry.report_id)
            .where(IncomeEntry.property_id.is_not(None))
            .where(IncomeEntry.reservation_id.is_(None))
            .where(IncomeEntry.restaurant_category.is_(None))
        )
    ).all()
    linked_income = 0
    for (inc_id, prop_id, rdate) in inc_rows:
        if not prop_id or not rdate:
            continue
        rid = (
            await session.execute(
                select(Reservation.id)
                .where(Reservation.property_id == prop_id)
                .where(Reservation.status.notin_([ReservationStatus.CANCELLED, ReservationStatus.NO_SHOW]))
                .where(Reservation.check_in <= rdate)
                .where(Reservation.check_out >= rdate)
                .order_by(Reservation.check_in.desc())
            )
        ).scalars().first()
        if rid:
            await session.execute(update(IncomeEntry).where(IncomeEntry.id == inc_id).values(reservation_id=rid))
            linked_income += 1
    await session.commit()

    return {"created": created, "skipped": skipped, "linked_income": linked_income}
