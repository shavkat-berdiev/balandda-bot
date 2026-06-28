"""Admin reservations + calendar API.

Backs the availability calendar in the dashboard: list bookings/blocks for a date
range, create a booking or manual block (double-booking is rejected by the DB
exclusion constraint -> 409), update, and cancel.
"""

from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth import get_current_user
from db.database import get_session
from db.enums import (
    PrepaymentStatus,
    RESERVATION_SOURCE_LABELS,
    RESERVATION_STATUS_LABELS,
    ReservationSource,
    ReservationStatus,
)
from db.models import Prepayment, Property, Reservation

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


def _out(r: Reservation, property_name: str | None = None) -> dict:
    st = r.status if isinstance(r.status, ReservationStatus) else ReservationStatus(r.status)
    sr = r.source if isinstance(r.source, ReservationSource) else ReservationSource(r.source)
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
        "total_amount": float(r.total_amount) if r.total_amount is not None else None,
        "deposit_amount": float(r.deposit_amount) if r.deposit_amount is not None else None,
        "note": r.note,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }


def _parse_status(value: str) -> ReservationStatus:
    try:
        return ReservationStatus(value)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"invalid status: {value}")


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
            select(Reservation, Property.name_ru)
            .join(Property, Property.id == Reservation.property_id)
            .where(Reservation.check_in < to)
            .where(Reservation.check_out > from_)
            .order_by(Reservation.property_id, Reservation.check_in)
        )
    ).all()
    return [_out(r, name) for (r, name) in rows]


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
    if data.status is not None:
        res.status = _parse_status(data.status)
    for field in ("check_in", "check_out", "guest_name", "guest_phone",
                  "guest_count", "total_amount", "deposit_amount", "note"):
        val = getattr(data, field)
        if val is not None:
            setattr(res, field, val)
    if res.check_out <= res.check_in:
        raise HTTPException(status_code=400, detail="check_out must be after check_in")
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(status_code=409, detail="Unit is not available for these dates")
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
    await session.refresh(res)
    return _out(res)


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
    return {"created": created, "skipped": skipped}
