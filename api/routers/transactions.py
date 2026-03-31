from datetime import date, datetime

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth import get_current_user
from db.database import get_session
from db.models import BusinessUnit, Category, Transaction, TransactionType

router = APIRouter()


class TransactionOut(BaseModel):
    id: int
    business_unit: str
    transaction_type: str
    amount: float
    note: str | None
    created_at: str
    category_name: str | None = None

    model_config = {"from_attributes": True}


@router.get("/", response_model=list[TransactionOut])
async def list_transactions(
    business_unit: BusinessUnit | None = None,
    transaction_type: TransactionType | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    limit: int = Query(default=50, le=200),
    session: AsyncSession = Depends(get_session),
    _user: dict = Depends(get_current_user),
):
    """List transactions with optional filters."""
    query = (
        select(Transaction, Category.name_ru)
        .join(Category, Transaction.category_id == Category.id)
        .order_by(Transaction.created_at.desc())
        .limit(limit)
    )

    if business_unit:
        query = query.where(Transaction.business_unit == business_unit)
    if transaction_type:
        query = query.where(Transaction.transaction_type == transaction_type)
    if date_from:
        query = query.where(Transaction.created_at >= datetime.combine(date_from, datetime.min.time()))
    if date_to:
        query = query.where(Transaction.created_at <= datetime.combine(date_to, datetime.max.time()))

    result = await session.execute(query)
    rows = result.all()

    return [
        TransactionOut(
            id=tx.id,
            business_unit=tx.business_unit.value,
            transaction_type=tx.transaction_type.value,
            amount=float(tx.amount),
            note=tx.note,
            created_at=tx.created_at.isoformat() if tx.created_at else "",
            category_name=cat_name,
        )
        for tx, cat_name in rows
    ]
