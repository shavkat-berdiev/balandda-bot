"""Card transactions API — reconciliation data for the web dashboard.

Feeds the future "Сверка переводов" page: list transactions with filters,
manually match/unmatch, or ignore a transaction. Owner-only.
"""

from datetime import date, datetime, time, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth import get_current_user, is_owner
from db.database import get_session
from db.models import CardTransaction

router = APIRouter()

_TZ = ZoneInfo("Asia/Tashkent")


def _require_owner(user: dict):
    if not is_owner(user):
        raise HTTPException(status_code=403, detail="Owner access required")


def _tx_out(tx: CardTransaction) -> dict:
    return {
        "id": tx.id,
        "card_last4": tx.card_last4,
        "business": tx.business,
        "direction": tx.direction,
        "tx_type": tx.tx_type,
        "amount": float(tx.amount),
        "merchant": tx.merchant,
        "tx_time": tx.tx_time.isoformat() if tx.tx_time else None,
        "balance_after": float(tx.balance_after) if tx.balance_after is not None else None,
        "match_status": tx.match_status,
        "matched_type": tx.matched_type,
        "matched_id": tx.matched_id,
        "match_note": tx.match_note,
    }


@router.get("")
async def list_card_transactions(
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    business: Optional[str] = Query(None, description="BALANDDA / XUSH"),
    status: Optional[str] = Query(None, description="NEW / MATCHED / UNMATCHED / IGNORED"),
    direction: Optional[str] = Query("IN"),
    limit: int = Query(200, le=1000),
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    _require_owner(user)
    q = select(CardTransaction).order_by(CardTransaction.tx_time.desc()).limit(limit)
    if date_from:
        q = q.where(CardTransaction.tx_time >= datetime.combine(date_from, time.min, tzinfo=_TZ))
    if date_to:
        q = q.where(
            CardTransaction.tx_time < datetime.combine(date_to, time.min, tzinfo=_TZ) + timedelta(days=1)
        )
    if business:
        q = q.where(CardTransaction.business == business.upper())
    if status:
        q = q.where(CardTransaction.match_status == status.upper())
    if direction:
        q = q.where(CardTransaction.direction == direction.upper())

    txs = (await session.execute(q)).scalars().all()

    # Summary for the same filter set
    totals = {"count": len(txs), "amount": sum(float(t.amount) for t in txs)}
    unmatched = [t for t in txs if t.match_status in ("NEW", "UNMATCHED")]
    totals["unmatched_count"] = len(unmatched)
    totals["unmatched_amount"] = sum(float(t.amount) for t in unmatched)

    return {"transactions": [_tx_out(t) for t in txs], "totals": totals}


class MatchBody(BaseModel):
    matched_type: str  # income_entry / prepayment / manual
    matched_id: Optional[int] = None
    note: Optional[str] = None


@router.post("/{tx_id}/match")
async def match_transaction(
    tx_id: int,
    body: MatchBody,
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    _require_owner(user)
    tx = await session.get(CardTransaction, tx_id)
    if tx is None:
        raise HTTPException(status_code=404, detail="Transaction not found")
    tx.match_status = "MATCHED"
    tx.matched_type = body.matched_type
    tx.matched_id = body.matched_id
    tx.match_note = body.note
    await session.commit()
    return _tx_out(tx)


@router.post("/{tx_id}/unmatch")
async def unmatch_transaction(
    tx_id: int,
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    _require_owner(user)
    tx = await session.get(CardTransaction, tx_id)
    if tx is None:
        raise HTTPException(status_code=404, detail="Transaction not found")
    tx.match_status = "UNMATCHED"
    tx.matched_type = None
    tx.matched_id = None
    tx.match_note = None
    await session.commit()
    return _tx_out(tx)


@router.post("/{tx_id}/ignore")
async def ignore_transaction(
    tx_id: int,
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    _require_owner(user)
    tx = await session.get(CardTransaction, tx_id)
    if tx is None:
        raise HTTPException(status_code=404, detail="Transaction not found")
    tx.match_status = "IGNORED"
    await session.commit()
    return _tx_out(tx)
