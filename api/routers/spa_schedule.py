"""SPA scheduling — appointments (service + master + room + time) with hard
conflict checks so a master or a room is never double-booked."""

from datetime import date as date_cls, datetime, timedelta, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import or_, select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth import get_current_user
from db.database import get_session
from db.enums import PAYMENT_METHOD_LABELS
from db.models import (
    IncomeEntry,
    PaymentMethod,
    Property,
    Reservation,
    ServiceItem,
    SpaAppointment,
    SpaCommissionPayout,
    StructuredReport,
)
from services import spa_commissions
from services.spa_payments import record_spa_payment
from services.spa_notify import notify_appointment_event
from sqlalchemy import func

router = APIRouter()

# Uzbekistan is a fixed UTC+5 (no DST).
TASHKENT = timezone(timedelta(hours=5))
STATUSES = {"planned", "done", "cancelled", "no_show"}


# ── Schemas ───────────────────────────────────────────────────────


class AppointmentCreate(BaseModel):
    service_id: int
    master_id: int
    start_at: datetime
    location_id: int | None = None
    reservation_id: int | None = None
    customer_name: str | None = None
    customer_phone: str | None = None
    price: float | None = None
    note: str | None = None
    status: str = "planned"


class AppointmentUpdate(BaseModel):
    service_id: int | None = None
    master_id: int | None = None
    start_at: datetime | None = None
    location_id: int | None = None
    reservation_id: int | None = None
    customer_name: str | None = None
    customer_phone: str | None = None
    price: float | None = None
    note: str | None = None
    status: str | None = None


class AppointmentOut(BaseModel):
    id: int
    service_id: int
    service_name: str
    duration_minutes: int
    master_id: int
    master_name: str
    location_id: int | None
    location_name: str | None
    reservation_id: int | None
    customer_name: str | None
    customer_phone: str | None
    start_at: datetime
    end_at: datetime
    status: str
    price: float
    paid: float = 0
    note: str | None


async def _paid_sum(session: AsyncSession, appt_id: int) -> float:
    return float(
        (
            await session.execute(
                select(func.coalesce(func.sum(IncomeEntry.amount), 0)).where(
                    IncomeEntry.spa_appointment_id == appt_id
                )
            )
        ).scalar() or 0
    )


def _out(a: SpaAppointment, paid: float = 0) -> AppointmentOut:
    return AppointmentOut(
        id=a.id,
        service_id=a.service_id,
        service_name=a.service.name_ru if a.service else "",
        duration_minutes=a.service.duration_minutes if a.service else 0,
        master_id=a.master_id,
        master_name=a.master.name if a.master else "",
        location_id=a.location_id,
        location_name=a.location.name_ru if a.location else None,
        reservation_id=a.reservation_id,
        customer_name=a.customer_name,
        customer_phone=a.customer_phone,
        start_at=a.start_at,
        end_at=a.end_at,
        status=a.status,
        price=float(a.price or 0),
        paid=paid,
        note=a.note,
    )


_OPTS = (
    selectinload(SpaAppointment.service),
    selectinload(SpaAppointment.master),
    selectinload(SpaAppointment.location),
)


async def _load(session: AsyncSession, appt_id: int) -> SpaAppointment | None:
    return (
        await session.execute(select(SpaAppointment).options(*_OPTS).where(SpaAppointment.id == appt_id))
    ).scalar_one_or_none()


async def _conflict(session: AsyncSession, master_id: int, location_id: int | None,
                    start: datetime, end: datetime, exclude_id: int | None = None):
    """Return ('master'|'room', other_appt) if the slot overlaps a live appointment."""
    def _overlap(col_field, value):
        stmt = select(SpaAppointment).options(*_OPTS).where(
            col_field == value,
            SpaAppointment.status != "cancelled",
            SpaAppointment.start_at < end,
            SpaAppointment.end_at > start,
        )
        if exclude_id:
            stmt = stmt.where(SpaAppointment.id != exclude_id)
        return stmt

    m = (await session.execute(_overlap(SpaAppointment.master_id, master_id))).scalars().first()
    if m:
        return ("master", m)
    if location_id:
        r = (await session.execute(_overlap(SpaAppointment.location_id, location_id))).scalars().first()
        if r:
            return ("room", r)
    return None


def _conflict_msg(kind: str, other: SpaAppointment) -> str:
    who = other.master.name if (kind == "master" and other.master) else (
        other.location.name_ru if other.location else "?")
    t = other.start_at.astimezone(TASHKENT).strftime("%H:%M")
    if kind == "master":
        return f"Мастер {who} уже занят в {t} ({other.service.name_ru if other.service else ''})."
    return f"Кабинет «{who}» уже занят в {t}."


# ── Endpoints ─────────────────────────────────────────────────────


@router.get("/appointments", response_model=list[AppointmentOut])
async def list_appointments(
    date: date_cls = Query(..., description="Day to list (YYYY-MM-DD, Asia/Tashkent)"),
    session: AsyncSession = Depends(get_session),
    user: dict = Depends(get_current_user),
):
    day_start = datetime(date.year, date.month, date.day, tzinfo=TASHKENT)
    day_end = day_start + timedelta(days=1)
    rows = (
        await session.execute(
            select(SpaAppointment).options(*_OPTS)
            .where(SpaAppointment.start_at >= day_start, SpaAppointment.start_at < day_end)
            .order_by(SpaAppointment.start_at)
        )
    ).scalars().all()
    paid_map = {
        aid: float(total or 0)
        for aid, total in (
            await session.execute(
                select(IncomeEntry.spa_appointment_id, func.sum(IncomeEntry.amount))
                .where(IncomeEntry.spa_appointment_id.in_([a.id for a in rows] or [0]))
                .group_by(IncomeEntry.spa_appointment_id)
            )
        ).all()
    }
    return [_out(a, paid_map.get(a.id, 0)) for a in rows]


@router.post("/appointments", response_model=AppointmentOut)
async def create_appointment(
    data: AppointmentCreate,
    session: AsyncSession = Depends(get_session),
    user: dict = Depends(get_current_user),
):
    if data.status not in STATUSES:
        raise HTTPException(status_code=422, detail="Invalid status")
    svc = (await session.execute(select(ServiceItem).where(ServiceItem.id == data.service_id))).scalar_one_or_none()
    if not svc:
        raise HTTPException(status_code=404, detail="Service not found")
    start = data.start_at
    end = start + timedelta(minutes=svc.duration_minutes or 0)
    if data.status != "cancelled":
        c = await _conflict(session, data.master_id, data.location_id, start, end)
        if c:
            raise HTTPException(status_code=409, detail=_conflict_msg(*c))
    appt = SpaAppointment(
        service_id=data.service_id,
        master_id=data.master_id,
        location_id=data.location_id,
        reservation_id=data.reservation_id,
        customer_name=(data.customer_name or None),
        customer_phone=(data.customer_phone or None),
        start_at=start,
        end_at=end,
        status=data.status,
        price=Decimal(str(data.price)) if data.price is not None else Decimal(str(svc.price)),
        note=(data.note or None),
        created_by=user.get("telegram_id"),
    )
    session.add(appt)
    await session.commit()
    loaded = await _load(session, appt.id)
    if loaded.status != "cancelled":
        await notify_appointment_event(session, loaded, "created")
    return _out(loaded, await _paid_sum(session, loaded.id))


@router.put("/appointments/{appt_id}", response_model=AppointmentOut)
async def update_appointment(
    appt_id: int,
    data: AppointmentUpdate,
    session: AsyncSession = Depends(get_session),
    user: dict = Depends(get_current_user),
):
    appt = await _load(session, appt_id)
    if not appt:
        raise HTTPException(status_code=404, detail="Appointment not found")
    updates = data.model_dump(exclude_unset=True)
    if "status" in updates and updates["status"] not in STATUSES:
        raise HTTPException(status_code=422, detail="Invalid status")
    old_status = appt.status
    old_master_id = appt.master_id
    old_start = appt.start_at

    new_service_id = updates.get("service_id", appt.service_id)
    new_start = updates.get("start_at", appt.start_at)
    new_master = updates.get("master_id", appt.master_id)
    new_location = updates.get("location_id", appt.location_id)
    new_status = updates.get("status", appt.status)

    # Recompute end if service or start changed.
    if "service_id" in updates or "start_at" in updates:
        svc = (await session.execute(select(ServiceItem).where(ServiceItem.id == new_service_id))).scalar_one_or_none()
        if not svc:
            raise HTTPException(status_code=404, detail="Service not found")
        new_end = new_start + timedelta(minutes=svc.duration_minutes or 0)
    else:
        new_end = appt.end_at

    if new_status != "cancelled":
        c = await _conflict(session, new_master, new_location, new_start, new_end, exclude_id=appt.id)
        if c:
            raise HTTPException(status_code=409, detail=_conflict_msg(*c))

    for field in ("service_id", "master_id", "location_id", "reservation_id",
                  "customer_name", "customer_phone", "note", "status"):
        if field in updates:
            setattr(appt, field, updates[field] or None if field in ("customer_name", "customer_phone", "note") else updates[field])
    if "start_at" in updates:
        appt.start_at = new_start
    appt.end_at = new_end
    if "price" in updates and updates["price"] is not None:
        appt.price = Decimal(str(updates["price"]))

    await session.commit()
    loaded = await _load(session, appt_id)

    # SPA bot notifications: pick ONE event for this change
    if loaded.status != old_status and loaded.status in ("cancelled", "done", "no_show"):
        await notify_appointment_event(session, loaded, loaded.status)
    elif loaded.status != "cancelled" and (
        loaded.master_id != old_master_id
        or loaded.start_at != old_start
        or "service_id" in updates
        or "location_id" in updates
    ):
        await notify_appointment_event(session, loaded, "updated")

    return _out(loaded, await _paid_sum(session, loaded.id))


# ── Reservation picker (link an appointment to a resort booking) ──


class ReservationLite(BaseModel):
    id: int
    guest_name: str | None
    guest_phone: str | None
    property_name: str | None
    check_in: date_cls
    check_out: date_cls


@router.get("/reservations-search", response_model=list[ReservationLite])
async def reservations_search(
    q: str = Query("", description="Guest name or phone fragment"),
    session: AsyncSession = Depends(get_session),
    user: dict = Depends(get_current_user),
):
    stmt = (
        select(Reservation, Property.name_ru)
        .join(Property, Property.id == Reservation.property_id, isouter=True)
        .order_by(Reservation.check_in.desc())
        .limit(15)
    )
    term = (q or "").strip()
    if term:
        like = f"%{term}%"
        stmt = stmt.where(or_(Reservation.guest_name.ilike(like), Reservation.guest_phone.ilike(like)))
    rows = (await session.execute(stmt)).all()
    return [
        ReservationLite(
            id=r.id, guest_name=r.guest_name, guest_phone=r.guest_phone,
            property_name=pname, check_in=r.check_in, check_out=r.check_out,
        )
        for (r, pname) in rows
    ]


# ── SPA payments (same flow as accommodation: draft report + income entry) ──


class SpaPaymentInput(BaseModel):
    amount: float
    payment_method: str


@router.post("/appointments/{appt_id}/payment", response_model=AppointmentOut)
async def accept_spa_payment(
    appt_id: int,
    data: SpaPaymentInput,
    session: AsyncSession = Depends(get_session),
    user: dict = Depends(get_current_user),
):
    appt = await _load(session, appt_id)
    if not appt:
        raise HTTPException(status_code=404, detail="Appointment not found")
    if appt.status == "cancelled":
        raise HTTPException(status_code=400, detail="Запись отменена — оплата невозможна")
    if data.amount is None or data.amount <= 0:
        raise HTTPException(status_code=400, detail="Сумма должна быть больше нуля")
    try:
        pm = PaymentMethod(data.payment_method)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Неверный способ оплаты: {data.payment_method}")
    operator = user.get("telegram_id")
    await record_spa_payment(session, appt, data.amount, pm, operator)
    await session.commit()
    return _out(await _load(session, appt_id), await _paid_sum(session, appt_id))


@router.get("/appointments/{appt_id}/payments")
async def list_spa_payments(
    appt_id: int,
    session: AsyncSession = Depends(get_session),
    user: dict = Depends(get_current_user),
):
    rows = (
        await session.execute(
            select(IncomeEntry, StructuredReport.report_date)
            .join(StructuredReport, StructuredReport.id == IncomeEntry.report_id)
            .where(IncomeEntry.spa_appointment_id == appt_id)
            .order_by(IncomeEntry.id.desc())
        )
    ).all()
    return [
        {
            "id": e.id,
            "amount": float(e.amount),
            "payment_method": e.payment_method.value,
            "payment_method_label": PAYMENT_METHOD_LABELS.get(e.payment_method, e.payment_method.value),
            "report_date": rd.isoformat(),
        }
        for (e, rd) in rows
    ]


# ── Commissions (per-master earnings + payouts) ───────────────────


@router.get("/commissions/summary")
async def commissions_summary(
    start_date: date_cls = Query(...),
    end_date: date_cls = Query(...),
    session: AsyncSession = Depends(get_session),
    user: dict = Depends(get_current_user),
):
    start, _ = spa_commissions.day_bounds(start_date)
    _, end = spa_commissions.day_bounds(end_date)
    rows = await spa_commissions.summary(session, start, end)
    return {
        "masters": rows,
        "totals": {
            "services_done": sum(r["services_done"] for r in rows),
            "revenue": sum(r["revenue"] for r in rows),
            "earned": sum(r["earned"] for r in rows),
            "paid_in_period": sum(r["paid_in_period"] for r in rows),
            "balance": sum(r["balance"] for r in rows),
        },
    }


@router.get("/commissions/details")
async def commissions_details(
    master_id: int = Query(...),
    start_date: date_cls = Query(...),
    end_date: date_cls = Query(...),
    session: AsyncSession = Depends(get_session),
    user: dict = Depends(get_current_user),
):
    start, _ = spa_commissions.day_bounds(start_date)
    _, end = spa_commissions.day_bounds(end_date)
    appts = await spa_commissions.done_appointments(session, start, end, master_id)
    payouts = (
        await session.execute(
            select(SpaCommissionPayout)
            .where(
                SpaCommissionPayout.master_id == master_id,
                SpaCommissionPayout.created_at >= start,
                SpaCommissionPayout.created_at < end,
            )
            .order_by(SpaCommissionPayout.created_at.desc())
        )
    ).scalars().all()
    return {
        "records": [
            {
                "id": a.id,
                "date": a.start_at.astimezone(TASHKENT).strftime("%d.%m.%Y %H:%M"),
                "service": a.service.name_ru if a.service else "—",
                "customer": a.customer_name,
                "price": float(a.price or 0),
                "commission": spa_commissions.commission_amount(a.service, a.master),
            }
            for a in appts
        ],
        "payouts": [
            {
                "id": p.id,
                "date": p.created_at.astimezone(TASHKENT).strftime("%d.%m.%Y %H:%M"),
                "amount": float(p.amount),
                "note": p.note,
            }
            for p in payouts
        ],
        "balance": await spa_commissions.master_balance(session, master_id),
    }
