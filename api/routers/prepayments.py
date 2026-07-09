"""Prepayment API endpoints for the admin panel."""

import os
import uuid
from datetime import date, timedelta
from typing import Optional

import aiohttp
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Response, UploadFile
from pydantic import BaseModel
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from api.auth import get_current_user, require_admin
from bot.config import settings
from db.database import get_session
from db.enums import PrepaymentStatus, PREPAYMENT_STATUS_LABELS, PaymentMethod, PAYMENT_METHOD_LABELS
from db.models import Prepayment, Property, Reservation

router = APIRouter()

UPLOAD_DIR = os.environ.get("UPLOAD_DIR", "/app/uploads")
PREPAY_DIR = os.path.join(UPLOAD_DIR, "prepay")


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
    # Keep the linked calendar reservation in sync (status change / cancellation)
    from db.reservation_sync import sync_reservation_for_prepayment
    await sync_reservation_for_prepayment(session, prepayment)

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


@router.get("/by-reservation/{reservation_id}")
async def prepayments_by_reservation(
    reservation_id: int,
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    rows = (
        await session.execute(
            select(Prepayment).where(Prepayment.reservation_id == reservation_id).order_by(Prepayment.created_at)
        )
    ).scalars().all()
    return [
        {
            "id": p.id,
            "amount": float(p.amount),
            "status": p.status.value,
            "status_label": PREPAYMENT_STATUS_LABELS.get(p.status, p.status.value),
            "note": p.note,
            "has_screenshot": bool(p.screenshot_url or p.screenshot_file_id),
            "created_at": p.created_at.isoformat() if p.created_at else None,
        }
        for p in rows
    ]


# ── Create a prepayment (with optional screenshot) linked to a reservation ──


@router.post("/from-reservation")
async def create_prepayment_from_reservation(
    reservation_id: int = Form(...),
    amount: float | None = Form(None),
    note: str | None = Form(None),
    screenshot: UploadFile | None = File(None),
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Agent adds a proof-of-payment screenshot for a booking. Saved to the SAME
    prepayments table as the bot flow. Amount is optional (the screenshot is just proof of
    what was already recorded) — defaults to the booking's deposit."""
    res = (
        await session.execute(select(Reservation).where(Reservation.id == reservation_id))
    ).scalar_one_or_none()
    if not res:
        raise HTTPException(404, "Reservation not found")
    if amount is None:
        amount = float(res.deposit_amount or 0)

    screenshot_url = None
    if screenshot is not None and (screenshot.filename or ""):
        data = await screenshot.read()
        if len(data) > 12 * 1024 * 1024:
            raise HTTPException(400, "Файл слишком большой (макс. 12 МБ)")
        ext = os.path.splitext(screenshot.filename)[1].lower()
        if ext not in (".jpg", ".jpeg", ".png", ".webp"):
            ext = ".jpg"
        os.makedirs(PREPAY_DIR, exist_ok=True)
        fname = f"{uuid.uuid4().hex}{ext}"
        with open(os.path.join(PREPAY_DIR, fname), "wb") as f:
            f.write(data)
        screenshot_url = f"prepay/{fname}"

    pre = Prepayment(
        guest_name=res.guest_name or "—",
        property_id=res.property_id,
        check_in_date=res.check_in,
        check_out_date=res.check_out,
        amount=amount,
        payment_method="CARD_TRANSFER",
        status=PrepaymentStatus.PENDING,
        screenshot_url=screenshot_url,
        note=note,
        operator_telegram_id=int(user.get("telegram_id") or 0),
        reservation_id=res.id,
    )
    session.add(pre)
    await session.commit()
    await session.refresh(pre)
    return {"ok": True, "id": pre.id, "has_screenshot": bool(screenshot_url)}


# ── Serve a screenshot image (disk file OR Telegram file_id) for inline viewing ──


@router.get("/screenshot-image/{prepayment_id}")
async def get_screenshot_image(
    prepayment_id: int,
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    p = (
        await session.execute(select(Prepayment).where(Prepayment.id == prepayment_id))
    ).scalar_one_or_none()
    if not p:
        raise HTTPException(404, "Not found")

    # Web-uploaded screenshot on disk.
    if p.screenshot_url:
        path = os.path.normpath(os.path.join(UPLOAD_DIR, p.screenshot_url))
        if not path.startswith(os.path.abspath(UPLOAD_DIR)) or not os.path.isfile(path):
            raise HTTPException(404, "File missing")
        with open(path, "rb") as f:
            data = f.read()
        media = "image/png" if path.endswith(".png") else "image/jpeg"
        return Response(content=data, media_type=media)

    # Bot-uploaded screenshot: fetch from Telegram by file_id.
    if p.screenshot_file_id and settings.bot_token:
        try:
            async with aiohttp.ClientSession() as s:
                async with s.get(
                    f"https://api.telegram.org/bot{settings.bot_token}/getFile",
                    params={"file_id": p.screenshot_file_id},
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as r:
                    j = await r.json()
                if not j.get("ok"):
                    raise HTTPException(404, "Telegram file not found")
                fp = j["result"]["file_path"]
                async with s.get(
                    f"https://api.telegram.org/file/bot{settings.bot_token}/{fp}",
                    timeout=aiohttp.ClientTimeout(total=15),
                ) as r2:
                    data = await r2.read()
            media = "image/png" if fp.endswith(".png") else "image/jpeg"
            return Response(content=data, media_type=media)
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(502, "Не удалось загрузить скриншот из Telegram")

    raise HTTPException(404, "No screenshot")


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
