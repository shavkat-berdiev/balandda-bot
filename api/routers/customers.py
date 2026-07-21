"""Guest base — search by phone (to suggest an existing record while booking), list, and
edit flags (VIP etc). Records are auto-created from bookings; this is for lookup + curation."""

import json

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth import get_current_user
from db.database import get_session
from db.models import Customer, Reservation

router = APIRouter()


def _norm_phone(raw: str | None) -> str | None:
    if not raw:
        return None
    d = "".join(ch for ch in raw if ch.isdigit())
    return d[-12:] if len(d) >= 9 else (d or None)


def _tags(c: Customer) -> list[str]:
    try:
        v = json.loads(c.tags) if c.tags else []
        return v if isinstance(v, list) else []
    except Exception:
        return []


def _out(c: Customer) -> dict:
    return {
        "id": c.id, "phone": c.phone_raw or c.phone, "name": c.name, "language": c.language,
        "telegram_username": c.telegram_username, "is_vip": c.is_vip, "tags": _tags(c),
        "notes": c.notes, "bookings_count": c.bookings_count,
        "created_at": c.created_at.isoformat() if c.created_at else None,
    }


@router.get("/search")
async def search(
    phone: str = Query("", description="Phone fragment (digits)"),
    session: AsyncSession = Depends(get_session),
    user: dict = Depends(get_current_user),
):
    """Find an existing guest by phone — used to suggest reusing a record while booking."""
    norm = _norm_phone(phone)
    if not norm or len(norm) < 5:
        return []
    rows = (
        await session.execute(
            select(Customer).where(Customer.phone.like(f"%{norm}%")).order_by(Customer.bookings_count.desc()).limit(8)
        )
    ).scalars().all()
    return [_out(c) for c in rows]


@router.get("")
async def list_customers(
    q: str = Query(""),
    session: AsyncSession = Depends(get_session),
    user: dict = Depends(get_current_user),
):
    stmt = select(Customer).order_by(Customer.updated_at.desc()).limit(200)
    term = (q or "").strip()
    if term:
        like = f"%{term}%"
        digits = _norm_phone(term)
        conds = [Customer.name.ilike(like)]
        if digits:
            conds.append(Customer.phone.like(f"%{digits}%"))
        stmt = select(Customer).where(or_(*conds)).order_by(Customer.updated_at.desc()).limit(200)
    rows = (await session.execute(stmt)).scalars().all()
    return [_out(c) for c in rows]


class CustomerUpdate(BaseModel):
    name: str | None = None
    is_vip: bool | None = None
    tags: list[str] | None = None
    notes: str | None = None


@router.put("/{cid}")
async def update_customer(
    cid: int,
    data: CustomerUpdate,
    session: AsyncSession = Depends(get_session),
    user: dict = Depends(get_current_user),
):
    c = await session.get(Customer, cid)
    if not c:
        raise HTTPException(status_code=404, detail="not found")
    if data.name is not None:
        c.name = data.name
    if data.is_vip is not None:
        c.is_vip = data.is_vip
    if data.tags is not None:
        c.tags = json.dumps(data.tags, ensure_ascii=False)
    if data.notes is not None:
        c.notes = data.notes
    await session.commit()
    await session.refresh(c)
    return _out(c)


@router.get("/{cid}/bookings")
async def customer_bookings(
    cid: int,
    session: AsyncSession = Depends(get_session),
    user: dict = Depends(get_current_user),
):
    rows = (
        await session.execute(
            select(Reservation).where(Reservation.customer_id == cid).order_by(Reservation.check_in.desc()).limit(50)
        )
    ).scalars().all()
    return [
        {"id": r.id, "check_in": r.check_in.isoformat(), "check_out": r.check_out.isoformat(),
         "status": r.status.value, "total_amount": float(r.total_amount) if r.total_amount is not None else None}
        for r in rows
    ]
