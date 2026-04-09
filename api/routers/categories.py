"""Category CRUD endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth import get_current_user, require_admin
from db.database import get_session
from db.models import BusinessUnit, Category, TransactionType

router = APIRouter()


class CategoryOut(BaseModel):
    id: int
    name_ru: str
    name_uz: str
    business_unit: str
    transaction_type: str
    is_active: bool
    sort_order: int

    model_config = {"from_attributes": True}


class CategoryCreate(BaseModel):
    name_ru: str
    name_uz: str
    business_unit: BusinessUnit
    transaction_type: TransactionType
    sort_order: int = 0


class CategoryUpdate(BaseModel):
    name_ru: str | None = None
    name_uz: str | None = None
    is_active: bool | None = None
    sort_order: int | None = None


@router.get("/", response_model=list[CategoryOut])
async def list_categories(
    business_unit: BusinessUnit | None = None,
    transaction_type: TransactionType | None = None,
    session: AsyncSession = Depends(get_session),
    _user: dict = Depends(get_current_user),
):
    """List all categories with optional filters."""
    query = select(Category).order_by(Category.business_unit, Category.transaction_type, Category.sort_order)
    if business_unit:
        query = query.where(Category.business_unit == business_unit)
    if transaction_type:
        query = query.where(Category.transaction_type == transaction_type)
    result = await session.execute(query)
    return result.scalars().all()


@router.post("/", response_model=CategoryOut)
async def create_category(
    data: CategoryCreate,
    session: AsyncSession = Depends(get_session),
    user: dict = Depends(get_current_user),
):
    """Create a new category (admin only)."""
    require_admin(user)

    category = Category(**data.model_dump())
    session.add(category)
    await session.commit()
    await session.refresh(category)
    return category


@router.put("/{category_id}", response_model=CategoryOut)
async def update_category(
    category_id: int,
    data: CategoryUpdate,
    session: AsyncSession = Depends(get_session),
    user: dict = Depends(get_current_user),
):
    """Update a category (admin only)."""
    require_admin(user)

    result = await session.execute(select(Category).where(Category.id == category_id))
    category = result.scalar_one_or_none()
    if not category:
        raise HTTPException(status_code=404, detail="Category not found")

    for field, value in data.model_dump(exclude_none=True).items():
        setattr(category, field, value)

    await session.commit()
    await session.refresh(category)
    return category


@router.delete("/{category_id}")
async def delete_category(
    category_id: int,
    session: AsyncSession = Depends(get_session),
    user: dict = Depends(get_current_user),
):
    """Deactivate a category (admin only). Doesn't delete to preserve history."""
    require_admin(user)

    result = await session.execute(select(Category).where(Category.id == category_id))
    category = result.scalar_one_or_none()
    if not category:
        raise HTTPException(status_code=404, detail="Category not found")

    category.is_active = False
    await session.commit()
    return {"status": "deactivated"}
