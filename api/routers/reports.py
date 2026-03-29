from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.database import get_session
from db.models import BusinessUnit, Category, Transaction, TransactionType

router = APIRouter()


class DailySummary(BaseModel):
    date: date
    business_unit: str
    total_in: float
    total_out: float
    net: float
    categories: list[dict]


@router.get("/daily", response_model=DailySummary)
async def daily_report(
    business_unit: BusinessUnit = Query(default=BusinessUnit.RESORT),
    report_date: date | None = None,
    session: AsyncSession = Depends(get_session),
):
    """Get daily summary for a business unit."""
    target_date = report_date or date.today()
    start = datetime.combine(target_date, datetime.min.time())
    end = datetime.combine(target_date, datetime.max.time())

    # Totals by type
    totals_query = (
        select(
            Transaction.transaction_type,
            func.coalesce(func.sum(Transaction.amount), 0).label("total"),
        )
        .where(
            Transaction.business_unit == business_unit,
            Transaction.created_at >= start,
            Transaction.created_at <= end,
        )
        .group_by(Transaction.transaction_type)
    )
    totals_result = await session.execute(totals_query)
    totals = {row.transaction_type: float(row.total) for row in totals_result}

    total_in = totals.get(TransactionType.CASH_IN, 0)
    total_out = totals.get(TransactionType.CASH_OUT, 0)

    # By category
    cat_query = (
        select(
            Category.name_ru,
            Transaction.transaction_type,
            func.sum(Transaction.amount).label("total"),
        )
        .join(Category, Transaction.category_id == Category.id)
        .where(
            Transaction.business_unit == business_unit,
            Transaction.created_at >= start,
            Transaction.created_at <= end,
        )
        .group_by(Category.name_ru, Transaction.transaction_type)
    )
    cat_result = await session.execute(cat_query)
    categories = [
        {"name": row.name_ru, "type": row.transaction_type.value, "total": float(row.total)}
        for row in cat_result
    ]

    return DailySummary(
        date=target_date,
        business_unit=business_unit.value,
        total_in=total_in,
        total_out=total_out,
        net=total_in - total_out,
        categories=categories,
    )
