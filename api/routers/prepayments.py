"""Prepayment API endpoints for the admin panel."""

from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from api.auth import get_current_user, require_admin
from db.database import get_session
from db.enums import PrepaymentStatus, PREPAYMENT_STATUS_LABELS, PaymentMethod, PAYMENT_METHOD_LABELS
from db.models import Prepayment, Property

router = APIRouter()


class PrepaymentStatusUpdate(BaseModel):
    status: str


# ── List prepayments (with optional date range & status filters) ──


@router.get("/list")
async def list_prepayments(
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """List all prepayments, optionally filtered by check-in date range and status."""
    query = (
        select(Prepayment)
        .options(selectinload(Prepayment.property))
        .order_by(Prepayment.check_in_date.desc(), Prepayment.created_at.desc())
    )

    filters = []
    if start_date:
        filters.append(Prepayment.check_in_date >= date.fromisoformat(start_date))
    if end_date:
        filters.append(Prepayment.check_in_date <= date.fromisoformat(end_date))
    if status:
        try:
            filters.append(Prepayment.status == PrepaymentStatus(status))
        except ValueError:
            pass

    if filters:
        query = query.where(and_(*filters))

    result = await session.execute(query)
    prepayments = result.scalars().all()

    return {
        "prepayments": [_serialize_prepayment(p) for p in prepayments],
        "total": len(prepayments),
        "total_amount": float(sum(p.amount for p in prepayments)),
    }


# ── Get single prepayment detail ──────────────────────────────────


@router.get("/detail/{prepayment_id}")
async def get_prepayment_detail(
    prepayment_id: int,
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Get full details of a single prepayment."""
    result = await session.execute(
        select(Prepayment)
        .options(selectinload(Prepayment.property))
        .where(Prepayment.id == prepayment_id)
    )
    prepayment = result.scalar_one_or_none()
    if not prepayment:
        raise HTTPException(404, "Prepayment not found")

    return _serialize_prepayment(prepayment)


# ── Update prepayment status ─────────────────────────────────────


@router.put("/status/{prepayment_id}")
async def update_prepayment_status(
    prepayment_id: int,
    body: PrepaymentStatusUpdate,
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Update prepayment status (admin only)."""
    require_admin(user)

    result = await session.execute(
        select(Prepayment).where(Prepayment.id == prepayment_id)
    )
    prepayment = result.scalar_one_or_none()
    if not prepayment:
        raise HTTPException(404, "Prepayment not found")

    try:
        new_status = PrepaymentStatus(body.status)
    except ValueError:
        raise HTTPException(400, f"Invalid status: {body.status}")

    prepayment.status = new_status
    await session.commit()
    await session.refresh(prepayment)

    return {"ok": True, "status": new_status.value}


# ── Dashboard/calendar summary ────────────────────────────────────


@router.get("/calendar")
async def prepayment_calendar(
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Get prepayments grouped by check-in date for calendar view."""
    if not start_date:
        start_date = date.today().replace(day=1).isoformat()
    if not end_date:
        # Default to end of current month + 1 month
        today = date.today()
        next_month = today.replace(day=28) + timedelta(days=4)
        end_date = next_month.replace(day=1).isoformat()

    result = await session.execute(
        select(Prepayment)
        .options(selectinload(Prepayment.property))
        .where(
            and_(
                Prepayment.check_in_date >= date.fromisoformat(start_date),
                Prepayment.check_in_date <= date.fromisoformat(end_date),
            )
        )
        .order_by(Prepayment.check_in_date.asc())
    )
    prepayments = result.scalars().all()

    # Group by date
    by_date = {}
    for p in prepayments:
        d = p.check_in_date.isoformat()
        if d not in by_date:
            by_date[d] = []
        by_date[d].append(_serialize_prepayment(p))

    # Summary stats
    total = len(prepayments)
    total_amount = float(sum(p.amount for p in prepayments))
    by_status = {}
    for p in prepayments:
        s = p.status.value
        by_status[s] = by_status.get(s, 0) + 1

    return {
        "by_date": by_date,
        "total": total,
        "total_amount": total_amount,
        "by_status": by_status,
    }


# ── Get screenshot (returns Telegram file_id for bot to forward) ──


@router.get("/screenshot/{prepayment_id}")
async def get_prepayment_screenshot(
    prepayment_id: int,
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Get the screenshot file_id for a prepayment."""
    result = await session.execute(
        select(Prepayment.screenshot_file_id).where(Prepayment.id == prepayment_id)
    )
    file_id = result.scalar_one_or_none()
    if not file_id:
        raise HTTPException(404, "No screenshot available")

    return {"file_id": file_id}


# ── Helpers ───────────────────────────────────────────────────────


def _serialize_prepayment(p: Prepayment) -> dict:
    return {
        "id": p.id,
        "guest_name": p.guest_name,
        "property_id": p.property_id,
        "property_name": p.property.name_ru if p.property else None,
        "property_emoji": p.property.emoji if p.property else "🏠",
        "check_in_date": p.check_in_date.isoformat(),
        "check_out_date": p.check_out_date.isoformat(),
        "nights": (p.check_out_date - p.check_in_date).days,
        "amount": float(p.amount),
        "payment_method": p.payment_method if p.payment_method else None,
        "payment_method_label": PAYMENT_METHOD_LABELS.get(
            PaymentMethod(p.payment_method) if p.payment_method else None, p.payment_method or ""
        ),
        "status": p.status.value,
        "status_label": PREPAYMENT_STATUS_LABELS.get(p.status, p.status.value),
        "has_screenshot": bool(p.screenshot_file_id),
        "operator_telegram_id": p.operator_telegram_id,
        "settled_in_report_id": p.settled_in_report_id,
        "created_at": p.created_at.isoformat() if p.created_at else None,
        "updated_at": p.updated_at.isoformat() if p.updated_at else None,
    }
