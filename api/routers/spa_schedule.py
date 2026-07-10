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
from db.models import Property, Reservation, ServiceItem, SpaAppointment

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
    note: str | None


def _out(a: SpaAppointment) -> AppointmentOut:
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
    return [_out(a) for a in rows]


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
    return _out(await _load(session, appt.id))


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
    return _out(await _load(session, appt_id))


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
