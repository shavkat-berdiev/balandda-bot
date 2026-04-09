"""Wallet API endpoints for the admin panel."""

from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth import get_current_user, is_owner
from db.database import get_session
from db.enums import (
    PaymentMethod,
    PAYMENT_METHOD_LABELS,
    WalletTransactionType,
    WALLET_TRANSACTION_TYPE_LABELS,
)
from db.models import IncomeEntry, StructuredReport, User, WalletTransaction

router = APIRouter()


async def _calculate_balance(session: AsyncSession, telegram_id: int) -> float:
    """Calculate cash wallet balance for a user."""
    # Incoming: CASH_IN + transfers received
    incoming = await session.execute(
        select(func.coalesce(func.sum(WalletTransaction.amount), 0)).where(
            or_(
                (WalletTransaction.sender_telegram_id == telegram_id) &
                (WalletTransaction.transaction_type == WalletTransactionType.CASH_IN),
                (WalletTransaction.receiver_telegram_id == telegram_id) &
                (WalletTransaction.transaction_type == WalletTransactionType.TRANSFER_TO_EMPLOYEE),
            )
        )
    )
    total_in = float(incoming.scalar())

    # Outgoing: sent transfers, to Shavkat, to bank
    outgoing = await session.execute(
        select(func.coalesce(func.sum(WalletTransaction.amount), 0)).where(
            WalletTransaction.sender_telegram_id == telegram_id,
            WalletTransaction.transaction_type.in_([
                WalletTransactionType.TRANSFER_TO_EMPLOYEE,
                WalletTransactionType.TRANSFER_TO_SHAVKAT,
                WalletTransactionType.CASH_TO_BANK,
            ]),
        )
    )
    total_out = float(outgoing.scalar())

    return total_in - total_out


# ── Cash wallets (per user) ──


@router.get("/list")
async def list_wallets(
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """List all users with their current cash wallet balances."""
    result = await session.execute(
        select(User).where(User.is_active == True).order_by(User.full_name)
    )
    users = result.scalars().all()

    wallets = []
    for u in users:
        balance = await _calculate_balance(session, u.telegram_id)
        wallets.append({
            "telegram_id": u.telegram_id,
            "full_name": u.full_name,
            "role": u.role.value,
            "balance": balance,
        })

    return {"wallets": wallets}


# ── Central payment-type wallets (owner only) ──


@router.get("/central")
async def central_wallets(
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    business_unit: Optional[str] = Query(None),
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Get total income per payment method (central wallets). Owner only."""
    if not is_owner(user):
        return {"wallets": [], "restricted": True}

    # Build filters
    filters = []
    if start_date:
        filters.append(StructuredReport.report_date >= date.fromisoformat(start_date))
    if end_date:
        filters.append(StructuredReport.report_date <= date.fromisoformat(end_date))
    if business_unit:
        filters.append(StructuredReport.business_unit == business_unit)

    query = (
        select(
            IncomeEntry.payment_method,
            func.sum(IncomeEntry.amount).label("total"),
            func.count(IncomeEntry.id).label("count"),
        )
        .join(StructuredReport, IncomeEntry.report_id == StructuredReport.id)
        .group_by(IncomeEntry.payment_method)
    )

    if filters:
        query = query.where(*filters)

    result = await session.execute(query)
    rows = result.all()

    wallets = []
    grand_total = 0
    for row in rows:
        pm = row.payment_method
        total = float(row.total or 0)
        grand_total += total
        wallets.append({
            "payment_method": pm.value if hasattr(pm, 'value') else str(pm),
            "label": PAYMENT_METHOD_LABELS.get(pm, str(pm)),
            "total": total,
            "count": row.count,
        })

    # Sort by total descending
    wallets.sort(key=lambda w: w["total"], reverse=True)

    return {"wallets": wallets, "grand_total": grand_total}


# ── Transaction history ──


@router.get("/transactions")
async def list_transactions(
    telegram_id: Optional[int] = Query(None),
    transaction_type: Optional[str] = Query(None),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    limit: int = Query(100, le=500),
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """List wallet transactions with optional filters."""
    query = (
        select(WalletTransaction)
        .order_by(WalletTransaction.created_at.desc())
        .limit(limit)
    )

    filters = []
    if telegram_id:
        filters.append(
            or_(
                WalletTransaction.sender_telegram_id == telegram_id,
                WalletTransaction.receiver_telegram_id == telegram_id,
            )
        )
    if transaction_type:
        try:
            filters.append(
                WalletTransaction.transaction_type == WalletTransactionType(transaction_type)
            )
        except ValueError:
            pass
    if start_date:
        filters.append(WalletTransaction.created_at >= date.fromisoformat(start_date))
    if end_date:
        end = date.fromisoformat(end_date) + timedelta(days=1)
        filters.append(WalletTransaction.created_at < end)

    if filters:
        query = query.where(*filters)

    result = await session.execute(query)
    txs = result.scalars().all()

    # Build a user name cache
    user_ids = set()
    for tx in txs:
        user_ids.add(tx.sender_telegram_id)
        if tx.receiver_telegram_id:
            user_ids.add(tx.receiver_telegram_id)

    user_map = {}
    if user_ids:
        users_result = await session.execute(
            select(User).where(User.telegram_id.in_(user_ids))
        )
        for u in users_result.scalars().all():
            user_map[u.telegram_id] = u.full_name

    transactions = []
    for tx in txs:
        transactions.append({
            "id": tx.id,
            "sender_telegram_id": tx.sender_telegram_id,
            "sender_name": user_map.get(tx.sender_telegram_id, "?"),
            "receiver_telegram_id": tx.receiver_telegram_id,
            "receiver_name": user_map.get(tx.receiver_telegram_id, "—") if tx.receiver_telegram_id else "—",
            "amount": float(tx.amount),
            "transaction_type": tx.transaction_type.value,
            "transaction_type_label": WALLET_TRANSACTION_TYPE_LABELS.get(
                tx.transaction_type, tx.transaction_type.value
            ),
            "note": tx.note,
            "business_unit": tx.business_unit.value if tx.business_unit else None,
            "created_at": tx.created_at.isoformat() if tx.created_at else None,
        })

    return {"transactions": transactions}


# ── Single user balance ──


@router.get("/balance/{telegram_id}")
async def get_balance(
    telegram_id: int,
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Get wallet balance for a specific user."""
    balance = await _calculate_balance(session, telegram_id)

    result = await session.execute(
        select(User).where(User.telegram_id == telegram_id)
    )
    u = result.scalar_one_or_none()

    return {
        "telegram_id": telegram_id,
        "full_name": u.full_name if u else "?",
        "balance": balance,
    }
