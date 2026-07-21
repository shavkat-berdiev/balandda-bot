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

import secrets

from api.auth import get_current_user, require_owner
from bot.config import settings
from services.beds24 import kick as beds24_kick
from db.database import get_session
from db.hold_timing import add_working_minutes
from services.customer_notify import (
    booking_cancelled_text,
    booking_changed_text,
    booking_confirmed_text,
    booking_payment_text,
    send_customer_message,
)
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
    telegram_username: str | None = None
    telegram_user_id: int | None = None
    status: str = "CONFIRMED"          # use "BLOCKED" for maintenance/owner holds; "HOLD" arms the unpaid timer
    source: str = "MANUAL"
    total_amount: float | None = None
    deposit_amount: float | None = None
    discount_percent: float | None = None
    discount_reason: str | None = None
    note: str | None = None


class PaymentInput(BaseModel):
    amount: float
    payment_method: str


class ReservationUpdate(BaseModel):
    property_id: int | None = None   # move the booking to a different unit/type
    check_in: date | None = None
    check_out: date | None = None
    guest_name: str | None = None
    guest_phone: str | None = None
    guest_count: int | None = None
    telegram_username: str | None = None
    telegram_user_id: int | None = None
    status: str | None = None
    total_amount: float | None = None
    deposit_amount: float | None = None
    discount_percent: float | None = None
    discount_reason: str | None = None
    note: str | None = None


def _norm_phone(raw: str | None) -> str | None:
    """Digits only, so +998 90 123-45-67 and 998901234567 match the same guest."""
    if not raw:
        return None
    d = "".join(ch for ch in raw if ch.isdigit())
    return d[-12:] if len(d) >= 9 else (d or None)


async def _upsert_customer(session: AsyncSession, *, phone: str | None, name: str | None,
                           language: str | None = None, tg_username: str | None = None,
                           tg_user_id: int | None = None) -> int | None:
    """Auto-save the guest by phone: create on first sight, refresh name/contact on repeat."""
    norm = _norm_phone(phone)
    if not norm:
        return None
    from db.models import Customer
    cust = (await session.execute(select(Customer).where(Customer.phone == norm))).scalar_one_or_none()
    if cust is None:
        cust = Customer(phone=norm, phone_raw=phone, name=name, language=language,
                        telegram_username=_clean_username(tg_username), telegram_user_id=tg_user_id,
                        bookings_count=1)
        session.add(cust)
        await session.flush()
    else:
        if name and not cust.name:
            cust.name = name
        if tg_username and not cust.telegram_username:
            cust.telegram_username = _clean_username(tg_username)
        if tg_user_id and not cust.telegram_user_id:
            cust.telegram_user_id = tg_user_id
        cust.bookings_count = (cust.bookings_count or 0) + 1
    return cust.id


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
    income = float(income_paid or 0)
    # The payment ledger is the single source of truth for "paid". deposit_amount is only
    # a fallback for legacy bookings prepaid via analytics with no ledger entry — this
    # avoids double-counting the 20% deposit hint on top of a recorded payment.
    paid = income if income > 0 else deposit
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
        "discount_percent": float(r.discount_percent or 0),
        "discount_reason": r.discount_reason,
        "customer_id": r.customer_id,
        "note": r.note,
        "telegram_username": r.telegram_username,
        "telegram_user_id": r.telegram_user_id,
        "hold_expires_at": r.hold_expires_at.isoformat() if r.hold_expires_at else None,
        "hold_warn_at": r.hold_warn_at.isoformat() if r.hold_warn_at else None,
        "hold_warned_at": r.hold_warned_at.isoformat() if r.hold_warned_at else None,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }


def _clean_username(u: str | None) -> str | None:
    if not u:
        return None
    u = u.strip().lstrip("@")
    return u or None


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


@router.get("/events")
async def all_reservation_events(
    limit: int = Query(300, le=2000),
    session: AsyncSession = Depends(get_session),
    user: dict = Depends(get_current_user),
):
    """Global change log across all bookings, newest first. Includes deletions —
    those rows have reservation_id = NULL (the booking is gone) but keep a snapshot
    in `detail`."""
    rows = (
        await session.execute(
            select(ReservationEvent, Reservation, Property)
            .outerjoin(Reservation, Reservation.id == ReservationEvent.reservation_id)
            .outerjoin(Property, Property.id == Reservation.property_id)
            .order_by(ReservationEvent.created_at.desc())
            .limit(limit)
        )
    ).all()
    return [
        {
            "id": e.id,
            "action": e.action,
            "actor_name": e.actor_name,
            "detail": e.detail,
            "created_at": e.created_at.isoformat() if e.created_at else None,
            "reservation_id": e.reservation_id,
            "property_name": prop.name_ru if prop else None,
            "guest_name": r.guest_name if r else None,
            "check_in": r.check_in.isoformat() if r else None,
            "check_out": r.check_out.isoformat() if r else None,
        }
        for (e, r, prop) in rows
    ]


@router.get("/inactive")
async def list_inactive(
    limit: int = Query(200, le=1000),
    session: AsyncSession = Depends(get_session),
    user: dict = Depends(get_current_user),
):
    """All cancelled + expired bookings (any date), newest first — so they can be
    reviewed and restored from the change-log page regardless of the calendar window."""
    rows = (
        await session.execute(
            select(Reservation, Property)
            .join(Property, Property.id == Reservation.property_id)
            .where(Reservation.status.in_([ReservationStatus.CANCELLED, ReservationStatus.EXPIRED]))
            .order_by(Reservation.updated_at.desc())
            .limit(limit)
        )
    ).all()
    return [
        {
            "id": r.id,
            "property_name": prop.name_ru if prop else None,
            "guest_name": r.guest_name,
            "telegram_username": r.telegram_username,
            "check_in": r.check_in.isoformat(),
            "check_out": r.check_out.isoformat(),
            "status": r.status.value if hasattr(r.status, "value") else r.status,
            "total_amount": float(r.total_amount) if r.total_amount is not None else None,
        }
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

    # An unpaid HOLD on an accommodation (RESORT) unit starts the working-hours
    # countdown (warn 30m, expire 60m). Pool units (RESTAURANT) never expire —
    # prepayment there is optional.
    now = datetime.now(timezone.utc)
    prop = await session.get(Property, data.property_id)
    arm = (
        status == ReservationStatus.HOLD
        and prop is not None
        and prop.business_unit == BusinessUnit.RESORT
    )

    # Price: explicit total wins; otherwise derive from the unit's rates and apply any discount.
    pct = float(data.discount_percent or 0)
    if data.total_amount is not None:
        total = float(data.total_amount)
    else:
        base = _stay_price(prop, data.check_in, data.check_out)
        total = round(base * (1 - pct / 100)) if base is not None else None
    # NEVER auto-fill deposit_amount: it is read as "already prepaid" by the paid/balance
    # calc, so filling it here would show an uncollected 30% prepayment on every booking.
    deposit = data.deposit_amount

    # Auto-save the guest by phone and link the record.
    customer_id = await _upsert_customer(
        session, phone=data.guest_phone, name=data.guest_name,
        tg_username=data.telegram_username, tg_user_id=data.telegram_user_id,
    )

    res = Reservation(
        property_id=data.property_id,
        check_in=data.check_in,
        check_out=data.check_out,
        guest_name=data.guest_name,
        guest_phone=data.guest_phone,
        guest_count=data.guest_count,
        telegram_username=_clean_username(data.telegram_username),
        telegram_user_id=data.telegram_user_id,
        status=status,
        source=source,
        total_amount=total,
        deposit_amount=deposit,
        discount_percent=pct,
        discount_reason=(data.discount_reason or None),
        customer_id=customer_id,
        note=data.note,
        created_by=user.get("telegram_id"),
        hold_warn_at=add_working_minutes(now, 30) if arm else None,
        hold_expires_at=add_working_minutes(now, 60) if arm else None,
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
    beds24_kick()
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
    old_property_id, old_ci, old_co = res.property_id, res.check_in, res.check_out
    if data.property_id is not None and data.property_id != res.property_id:
        res.property_id = data.property_id
    if data.status is not None:
        res.status = _parse_status(data.status)
    for field in ("check_in", "check_out", "guest_name", "guest_phone",
                  "guest_count", "total_amount", "deposit_amount", "note"):
        val = getattr(data, field)
        if val is not None:
            setattr(res, field, val)
    if data.telegram_username is not None:
        res.telegram_username = _clean_username(data.telegram_username)
    if data.telegram_user_id is not None:
        res.telegram_user_id = data.telegram_user_id
    if data.discount_percent is not None:
        res.discount_percent = data.discount_percent
    if data.discount_reason is not None:
        res.discount_reason = data.discount_reason or None
    if res.check_out <= res.check_in:
        raise HTTPException(status_code=400, detail="check_out must be after check_in")

    # Re-price when the booking moves (new unit/dates) OR the discount changes — from the
    # unit's rates with the discount applied — unless the caller set an explicit price.
    moved = (res.property_id != old_property_id) or (res.check_in != old_ci) or (res.check_out != old_co)
    if (moved or data.discount_percent is not None) and data.total_amount is None:
        prop_new = await session.get(Property, res.property_id)
        base = _stay_price(prop_new, res.check_in, res.check_out)
        if base is not None:
            pct = float(res.discount_percent or 0)
            res.total_amount = round(base * (1 - pct / 100))
            # Do NOT touch deposit_amount — it is read as "already prepaid".

    # Keep the guest base fresh if phone/name changed here.
    if data.guest_phone is not None or data.guest_name is not None:
        cid = await _upsert_customer(session, phone=res.guest_phone, name=res.guest_name,
                                     tg_username=res.telegram_username, tg_user_id=res.telegram_user_id)
        if cid:
            res.customer_id = cid

    new = {f: getattr(res, f) for f in _FIELDS}
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(status_code=409, detail="Unit is not available for these dates")
    detail = _diff_text(old, new)
    if res.property_id != old_property_id:
        detail = ("Смена объекта; " + detail) if detail else "Смена объекта"
    if detail:
        await _log(session, res_id, user, "updated", detail)
    # Notify the customer if the unit or the dates changed.
    if res.telegram_user_id and (res.property_id != old_property_id or res.check_in != old_ci or res.check_out != old_co):
        prop = await session.get(Property, res.property_id)
        await send_customer_message(res.telegram_user_id, booking_changed_text(res, prop.name_ru if prop else ""))
    await session.refresh(res)
    beds24_kick()
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
    if res.telegram_user_id:
        prop = await session.get(Property, res.property_id)
        await send_customer_message(res.telegram_user_id, booking_cancelled_text(res, prop.name_ru if prop else ""))
    await session.refresh(res)
    beds24_kick()
    return _out(res)


@router.post("/{res_id}/extend-hold")
async def extend_hold(
    res_id: int,
    session: AsyncSession = Depends(get_session),
    user: dict = Depends(get_current_user),
):
    """Give an unpaid hold 24 more hours to be prepaid (agent confirmed the customer is
    real). Re-arms a reminder ~1h before the new deadline."""
    res = await session.get(Reservation, res_id)
    if not res:
        raise HTTPException(status_code=404, detail="not found")
    if res.status != ReservationStatus.HOLD:
        raise HTTPException(status_code=400, detail="Продлевать можно только бронь, ожидающую предоплаты")
    now = datetime.now(timezone.utc)
    res.hold_expires_at = now + timedelta(hours=24)
    res.hold_warn_at = now + timedelta(hours=23)
    res.hold_warned_at = None
    await session.commit()
    await _log(session, res_id, user, "updated", "Окно предоплаты продлено до 24 часов")
    await session.refresh(res)
    return await _reservation_out(session, res)


@router.post("/{res_id}/waive-prepayment")
async def waive_prepayment(
    res_id: int,
    session: AsyncSession = Depends(get_session),
    user: dict = Depends(get_current_user),
):
    """Confirm a booking without requiring prepayment (contract guests, arriving from
    abroad, etc.). Stops the expiry timer; a payment can still be added later."""
    res = await session.get(Reservation, res_id)
    if not res:
        raise HTTPException(status_code=404, detail="not found")
    if res.status != ReservationStatus.HOLD:
        raise HTTPException(status_code=400, detail="Действие доступно только для брони, ожидающей предоплаты")
    res.status = ReservationStatus.CONFIRMED
    res.hold_warn_at = None
    res.hold_expires_at = None
    res.hold_warned_at = None
    await session.commit()
    await _log(session, res_id, user, "updated", "Подтверждено без предоплаты")
    await _notify_confirmed(session, res)
    await session.refresh(res)
    return await _reservation_out(session, res)


async def _notify_confirmed(session: AsyncSession, res: Reservation) -> None:
    """Send the customer the final booking-confirmed message once (if we have their ID)."""
    if not res.telegram_user_id or res.confirmed_notified_at:
        return
    prop = await session.get(Property, res.property_id)
    if await send_customer_message(res.telegram_user_id, booking_confirmed_text(res, prop.name_ru if prop else "")):
        res.confirmed_notified_at = datetime.now(timezone.utc)
        await session.commit()


@router.post("/{res_id}/connect-link")
async def connect_link(
    res_id: int,
    session: AsyncSession = Depends(get_session),
    user: dict = Depends(get_current_user),
):
    """Return a t.me/@balandda_bot deep-link the agent sends the customer; tapping it
    links their Telegram to this booking and triggers the booking-received message."""
    res = await session.get(Reservation, res_id)
    if not res:
        raise HTTPException(status_code=404, detail="not found")
    if not res.connect_token:
        res.connect_token = secrets.token_urlsafe(12)[:16]
        await session.commit()
    return {
        "url": f"https://t.me/{settings.customer_bot_username}?start=connect_{res.connect_token}",
        "token": res.connect_token,
    }


@router.post("/{res_id}/restore")
async def restore_reservation(
    res_id: int,
    session: AsyncSession = Depends(get_session),
    user: dict = Depends(get_current_user),
):
    """Bring a CANCELLED or EXPIRED booking back as CONFIRMED. Rejected with 409 if the
    dates are now taken by another active booking."""
    res = await session.get(Reservation, res_id)
    if not res:
        raise HTTPException(status_code=404, detail="not found")
    if res.status not in (ReservationStatus.CANCELLED, ReservationStatus.EXPIRED):
        raise HTTPException(status_code=400, detail="Бронь активна — восстанавливать нечего")
    res.status = ReservationStatus.CONFIRMED
    res.hold_warn_at = None
    res.hold_expires_at = None
    res.hold_warned_at = None
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(
            status_code=409,
            detail="Даты уже заняты другой бронью — освободите их перед восстановлением",
        )
    await _log(session, res_id, user, "restored", "Бронь восстановлена")
    await session.refresh(res)
    beds24_kick()
    return _out(res)


@router.delete("/{res_id}")
async def delete_reservation(
    res_id: int,
    session: AsyncSession = Depends(get_session),
    user: dict = Depends(get_current_user),
):
    """Permanently remove a booking (owner only, and only if already cancelled).
    Linked accommodation income is kept but unlinked; a surviving audit row records
    the deletion (its reservation_id becomes NULL by FK ON DELETE SET NULL)."""
    require_owner(user)
    res = await session.get(Reservation, res_id)
    if not res:
        raise HTTPException(status_code=404, detail="not found")
    if res.status not in (ReservationStatus.CANCELLED, ReservationStatus.EXPIRED):
        raise HTTPException(status_code=400, detail="Удалить навсегда можно только отменённую или истёкшую бронь")
    prop = await session.get(Property, res.property_id)
    snapshot = (
        f"{res.guest_name or 'без имени'} · "
        f"{prop.name_ru if prop else res.property_id} · "
        f"{res.check_in}→{res.check_out}"
    )
    await session.execute(
        update(IncomeEntry).where(IncomeEntry.reservation_id == res_id).values(reservation_id=None)
    )
    await _log(session, res_id, user, "deleted", f"Бронь удалена навсегда: {snapshot}")
    await session.delete(res)
    await session.commit()
    beds24_kick()
    return {"ok": True, "deleted": res_id}


# ---- payment ledger helpers ----
def _today_tashkent() -> date:
    return datetime.now(timezone(timedelta(hours=5))).date()


async def _get_or_create_report(session: AsyncSession, operator: int,
                                business_unit: BusinessUnit = BusinessUnit.RESORT) -> StructuredReport:
    """Today's draft report for this operator + business unit (created on demand).
    Accommodation is RESORT; pool units are RESTAURANT — so each lands in its own report."""
    report = (
        await session.execute(
            select(StructuredReport).where(
                StructuredReport.submitted_by == operator,
                StructuredReport.report_date == _today_tashkent(),
                StructuredReport.business_unit == business_unit,
                StructuredReport.status == ReportStatus.DRAFT,
            )
        )
    ).scalar_one_or_none()
    if not report:
        report = StructuredReport(
            report_date=_today_tashkent(), business_unit=business_unit,
            status=ReportStatus.DRAFT, submitted_by=operator,
        )
        session.add(report)
        await session.flush()
    return report


async def _reservation_out(session: AsyncSession, res: Reservation) -> dict:
    income = (
        await session.execute(
            select(func.coalesce(func.sum(IncomeEntry.amount), 0)).where(IncomeEntry.reservation_id == res.id)
        )
    ).scalar() or 0
    prop = await session.get(Property, res.property_id)
    total = float(res.total_amount) if res.total_amount is not None else _stay_price(prop, res.check_in, res.check_out)
    return _out(res, prop.name_ru if prop else None, float(income), total)


async def _actor_name(session: AsyncSession, operator: int) -> str | None:
    return (
        await session.execute(select(User.full_name).where(User.telegram_id == operator))
    ).scalar_one_or_none()


@router.post("/{res_id}/payment")
async def accept_payment(
    res_id: int,
    data: PaymentInput,
    session: AsyncSession = Depends(get_session),
    user: dict = Depends(get_current_user),
):
    """Add a (partial) accommodation payment from the calendar. Records it as income in
    today's RESORT report (lands in analytics immediately), mirrors it into the Prepayment
    table (finance source of truth), tops up the cash wallet if paid in cash, and — on the
    first payment — flips an unpaid HOLD to CONFIRMED and stops the expiry countdown."""
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
    prop = await session.get(Property, res.property_id)
    business_unit = prop.business_unit if prop and prop.business_unit else BusinessUnit.RESORT
    report = await _get_or_create_report(session, operator, business_unit)

    amt = round(float(data.amount))
    nights = (res.check_out - res.check_in).days or 1
    income = IncomeEntry(
        report_id=report.id, property_id=res.property_id, reservation_id=res.id,
        payment_method=pm, amount=amt, num_days=nights,
    )
    session.add(income)
    await session.flush()  # need income.id for the mirror
    report.total_income = (report.total_income or 0) + amt
    if pm == PaymentMethod.CASH:
        session.add(WalletTransaction(
            sender_telegram_id=operator, amount=amt,
            transaction_type=WalletTransactionType.CASH_IN,
            status=WalletTransactionStatus.COMPLETED,
            report_id=report.id, business_unit=business_unit,
        ))
    # Mirror into the Prepayment table — analytics stays the finance source of truth.
    session.add(Prepayment(
        guest_name=res.guest_name or "—", property_id=res.property_id,
        check_in_date=res.check_in, check_out_date=res.check_out,
        amount=amt, payment_method=pm.value, status=PrepaymentStatus.CONFIRMED,
        operator_telegram_id=operator, reservation_id=res.id, income_entry_id=income.id,
        settled_in_report_id=report.id, note="Из календаря броней",
    ))

    # First payment secures the booking: HOLD (red) -> CONFIRMED, stop the countdown.
    if res.status == ReservationStatus.HOLD:
        res.status = ReservationStatus.CONFIRMED
        res.hold_warn_at = None
        res.hold_expires_at = None
        res.hold_warned_at = None

    name = await _actor_name(session, operator)
    session.add(ReservationEvent(
        reservation_id=res.id, actor_id=operator, actor_name=name, action="payment",
        detail=f"Оплата: +{amt} сум ({PAYMENT_METHOD_LABELS.get(pm, pm.value)}) · отчёт #{report.id}",
    ))
    await session.commit()
    # Tell the customer their payment was received (amount + running balance).
    if res.telegram_user_id:
        prop2 = await session.get(Property, res.property_id)
        paid_sum = (await session.execute(
            select(func.coalesce(func.sum(IncomeEntry.amount), 0)).where(IncomeEntry.reservation_id == res.id)
        )).scalar() or 0
        total_amt = float(res.total_amount) if res.total_amount is not None else _stay_price(prop2, res.check_in, res.check_out)
        await send_customer_message(
            res.telegram_user_id,
            booking_payment_text(res, prop2.name_ru if prop2 else "", amt, float(paid_sum), total_amt),
        )
    await session.refresh(res)
    return await _reservation_out(session, res)


@router.get("/{res_id}/payments")
async def list_payments(
    res_id: int,
    session: AsyncSession = Depends(get_session),
    user: dict = Depends(get_current_user),
):
    """The payment ledger for a booking — every partial payment, newest first."""
    rows = (
        await session.execute(
            select(IncomeEntry, StructuredReport.report_date)
            .join(StructuredReport, StructuredReport.id == IncomeEntry.report_id)
            .where(IncomeEntry.reservation_id == res_id)
            .order_by(IncomeEntry.id.desc())
        )
    ).all()
    return [
        {
            "id": e.id,
            "amount": float(e.amount),
            "payment_method": e.payment_method.value if e.payment_method else None,
            "payment_method_label": PAYMENT_METHOD_LABELS.get(
                e.payment_method, e.payment_method.value if e.payment_method else ""),
            "report_id": e.report_id,
            "report_date": rd.isoformat() if rd else None,
        }
        for (e, rd) in rows
    ]


@router.patch("/{res_id}/payments/{income_id}")
async def edit_payment(
    res_id: int,
    income_id: int,
    data: PaymentInput,
    session: AsyncSession = Depends(get_session),
    user: dict = Depends(get_current_user),
):
    """Edit a partial payment's amount/method; keeps the report total, cash wallet and the
    mirrored Prepayment in sync, and logs the change."""
    income = await session.get(IncomeEntry, income_id)
    if not income or income.reservation_id != res_id:
        raise HTTPException(status_code=404, detail="payment not found")
    if data.amount is None or data.amount <= 0:
        raise HTTPException(status_code=400, detail="amount must be positive")
    try:
        new_pm = PaymentMethod(data.payment_method)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"invalid payment_method: {data.payment_method}")

    operator = user.get("telegram_id")
    old_amt = round(float(income.amount))
    old_pm = income.payment_method
    new_amt = round(float(data.amount))

    report = await session.get(StructuredReport, income.report_id)
    if report is not None:
        report.total_income = (report.total_income or 0) + (new_amt - old_amt)

    # Cash on hand: apply a signed wallet adjustment for the net cash change.
    old_cash = old_amt if old_pm == PaymentMethod.CASH else 0
    new_cash = new_amt if new_pm == PaymentMethod.CASH else 0
    if new_cash - old_cash != 0 and report is not None:
        session.add(WalletTransaction(
            sender_telegram_id=report.submitted_by, amount=(new_cash - old_cash),
            transaction_type=WalletTransactionType.ADJUSTMENT,
            status=WalletTransactionStatus.COMPLETED,
            report_id=income.report_id, business_unit=report.business_unit,
            note="Правка оплаты брони",
        ))

    income.amount = new_amt
    income.payment_method = new_pm

    prep = (
        await session.execute(select(Prepayment).where(Prepayment.income_entry_id == income_id))
    ).scalar_one_or_none()
    if prep is not None:
        prep.amount = new_amt
        prep.payment_method = new_pm.value

    name = await _actor_name(session, operator)
    session.add(ReservationEvent(
        reservation_id=res_id, actor_id=operator, actor_name=name, action="payment",
        detail=f"Правка оплаты: {old_amt} → {new_amt} сум ({PAYMENT_METHOD_LABELS.get(new_pm, new_pm.value)})",
    ))
    await session.commit()
    res = await session.get(Reservation, res_id)
    return await _reservation_out(session, res)


@router.delete("/{res_id}/payments/{income_id}")
async def delete_payment(
    res_id: int,
    income_id: int,
    session: AsyncSession = Depends(get_session),
    user: dict = Depends(get_current_user),
):
    """Remove a partial payment; reverses report income, cash wallet and the mirrored
    Prepayment, and logs it."""
    income = await session.get(IncomeEntry, income_id)
    if not income or income.reservation_id != res_id:
        raise HTTPException(status_code=404, detail="payment not found")
    operator = user.get("telegram_id")
    amt = round(float(income.amount))
    pm = income.payment_method
    report = await session.get(StructuredReport, income.report_id)
    if report is not None:
        report.total_income = (report.total_income or 0) - amt
        if pm == PaymentMethod.CASH:
            session.add(WalletTransaction(
                sender_telegram_id=report.submitted_by, amount=-amt,
                transaction_type=WalletTransactionType.ADJUSTMENT,
                status=WalletTransactionStatus.COMPLETED,
                report_id=income.report_id, business_unit=report.business_unit,
                note="Удаление оплаты брони",
            ))
    # Delete the mirrored prepayment first (its FK to the income row is SET NULL on delete).
    prep = (
        await session.execute(select(Prepayment).where(Prepayment.income_entry_id == income_id))
    ).scalar_one_or_none()
    if prep is not None:
        await session.delete(prep)
    name = await _actor_name(session, operator)
    session.add(ReservationEvent(
        reservation_id=res_id, actor_id=operator, actor_name=name, action="payment",
        detail=f"Удаление оплаты: −{amt} сум ({PAYMENT_METHOD_LABELS.get(pm, pm.value if pm else '')})",
    ))
    await session.delete(income)
    await session.commit()
    res = await session.get(Reservation, res_id)
    return await _reservation_out(session, res)


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
