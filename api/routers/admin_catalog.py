"""Admin CRUD endpoints for catalog items (properties, services, minibar, staff)."""

from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth import get_current_user, require_admin
from db.database import get_session
from db.enums import (
    PROPERTY_TYPE_LABELS,
    SERVICE_TYPE_LABELS,
    PropertyType,
    ServiceType,
)
from db.models import (
    BusinessUnit,
    MinibarItem,
    Property,
    ServiceItem,
    StaffMember,
)

router = APIRouter()


def _require_admin(user: dict):
    require_admin(user)


# ── Property schemas ──────────────────────────────────────────────


class PropertyCreate(BaseModel):
    code: str
    name_ru: str
    name_uz: str
    property_type: str
    unit_number: str | None = None
    capacity: int = 2
    has_sauna: bool = False
    price_weekday: float = 0
    price_weekend: float = 0
    emoji: str = "🏠"
    sort_order: int = 0
    business_unit: str = "RESORT"


class PropertyUpdate(BaseModel):
    code: str | None = None
    name_ru: str | None = None
    name_uz: str | None = None
    property_type: str | None = None
    unit_number: str | None = None
    capacity: int | None = None
    has_sauna: bool | None = None
    price_weekday: float | None = None
    price_weekend: float | None = None
    emoji: str | None = None
    sort_order: int | None = None
    is_active: bool | None = None


class PropertyOut(BaseModel):
    id: int
    code: str
    name_ru: str
    name_uz: str
    property_type: str
    property_type_label: str
    unit_number: str | None
    capacity: int
    has_sauna: bool
    price_weekday: float
    price_weekend: float
    emoji: str
    is_active: bool
    sort_order: int
    business_unit: str


# ── Service schemas ───────────────────────────────────────────────


class ServiceCreate(BaseModel):
    service_type: str
    name_ru: str
    name_uz: str
    duration_minutes: int = 0
    price: float = 0
    sort_order: int = 0


class ServiceUpdate(BaseModel):
    service_type: str | None = None
    name_ru: str | None = None
    name_uz: str | None = None
    duration_minutes: int | None = None
    price: float | None = None
    sort_order: int | None = None
    is_active: bool | None = None


class ServiceOut(BaseModel):
    id: int
    service_type: str
    service_type_label: str
    name_ru: str
    name_uz: str
    duration_minutes: int
    price: float
    is_active: bool
    sort_order: int


# ── Minibar schemas ───────────────────────────────────────────────


class MinibarCreate(BaseModel):
    name_ru: str
    name_uz: str
    price: float = 0
    sort_order: int = 0


class MinibarUpdate(BaseModel):
    name_ru: str | None = None
    name_uz: str | None = None
    price: float | None = None
    sort_order: int | None = None
    is_active: bool | None = None


class MinibarOut(BaseModel):
    id: int
    name_ru: str
    name_uz: str
    price: float
    is_active: bool
    sort_order: int


# ── Staff schemas ─────────────────────────────────────────────────


class StaffCreate(BaseModel):
    name: str
    role_description: str | None = None


class StaffUpdate(BaseModel):
    name: str | None = None
    role_description: str | None = None
    is_active: bool | None = None


class StaffOut(BaseModel):
    id: int
    name: str
    role_description: str | None
    is_active: bool


# ── Enum listing endpoint ────────────────────────────────────────


@router.get("/enums")
async def list_enums(user: dict = Depends(get_current_user)):
    """Return available enum values for dropdowns."""
    return {
        "property_types": [
            {"value": pt.value, "label": PROPERTY_TYPE_LABELS.get(pt, pt.value)}
            for pt in PropertyType
        ],
        "service_types": [
            {"value": st.value, "label": SERVICE_TYPE_LABELS.get(st, st.value)}
            for st in ServiceType
        ],
        "business_units": [
            {"value": bu.value, "label": bu.value}
            for bu in BusinessUnit
        ],
    }


# ── Property CRUD ─────────────────────────────────────────────────


def _property_out(p: Property) -> PropertyOut:
    return PropertyOut(
        id=p.id,
        code=p.code,
        name_ru=p.name_ru,
        name_uz=p.name_uz,
        property_type=p.property_type.value,
        property_type_label=PROPERTY_TYPE_LABELS.get(p.property_type, p.property_type.value),
        unit_number=p.unit_number,
        capacity=p.capacity,
        has_sauna=p.has_sauna,
        price_weekday=float(p.price_weekday),
        price_weekend=float(p.price_weekend),
        emoji=p.emoji or "🏠",
        is_active=p.is_active,
        sort_order=p.sort_order,
        business_unit=p.business_unit.value,
    )


@router.get("/properties", response_model=list[PropertyOut])
async def list_properties(
    session: AsyncSession = Depends(get_session),
    user: dict = Depends(get_current_user),
):
    result = await session.execute(select(Property).order_by(Property.sort_order))
    return [_property_out(p) for p in result.scalars().all()]


@router.post("/properties", response_model=PropertyOut)
async def create_property(
    data: PropertyCreate,
    session: AsyncSession = Depends(get_session),
    user: dict = Depends(get_current_user),
):
    _require_admin(user)
    prop = Property(
        code=data.code,
        name_ru=data.name_ru,
        name_uz=data.name_uz,
        property_type=PropertyType(data.property_type),
        unit_number=data.unit_number,
        capacity=data.capacity,
        has_sauna=data.has_sauna,
        price_weekday=Decimal(str(data.price_weekday)),
        price_weekend=Decimal(str(data.price_weekend)),
        emoji=data.emoji,
        sort_order=data.sort_order,
        business_unit=BusinessUnit(data.business_unit),
    )
    session.add(prop)
    await session.commit()
    await session.refresh(prop)
    return _property_out(prop)


@router.put("/properties/{item_id}", response_model=PropertyOut)
async def update_property(
    item_id: int,
    data: PropertyUpdate,
    session: AsyncSession = Depends(get_session),
    user: dict = Depends(get_current_user),
):
    _require_admin(user)
    result = await session.execute(select(Property).where(Property.id == item_id))
    prop = result.scalar_one_or_none()
    if not prop:
        raise HTTPException(status_code=404, detail="Property not found")

    updates = data.model_dump(exclude_none=True)
    if "property_type" in updates:
        updates["property_type"] = PropertyType(updates["property_type"])
    if "price_weekday" in updates:
        updates["price_weekday"] = Decimal(str(updates["price_weekday"]))
    if "price_weekend" in updates:
        updates["price_weekend"] = Decimal(str(updates["price_weekend"]))

    for field, value in updates.items():
        setattr(prop, field, value)

    await session.commit()
    await session.refresh(prop)
    return _property_out(prop)


# ── Service CRUD ──────────────────────────────────────────────────


def _service_out(s: ServiceItem) -> ServiceOut:
    return ServiceOut(
        id=s.id,
        service_type=s.service_type.value,
        service_type_label=SERVICE_TYPE_LABELS.get(s.service_type, s.service_type.value),
        name_ru=s.name_ru,
        name_uz=s.name_uz,
        duration_minutes=s.duration_minutes,
        price=float(s.price),
        is_active=s.is_active,
        sort_order=s.sort_order,
    )


@router.get("/services", response_model=list[ServiceOut])
async def list_services(
    session: AsyncSession = Depends(get_session),
    user: dict = Depends(get_current_user),
):
    result = await session.execute(select(ServiceItem).order_by(ServiceItem.sort_order))
    return [_service_out(s) for s in result.scalars().all()]


@router.post("/services", response_model=ServiceOut)
async def create_service(
    data: ServiceCreate,
    session: AsyncSession = Depends(get_session),
    user: dict = Depends(get_current_user),
):
    _require_admin(user)
    svc = ServiceItem(
        service_type=ServiceType(data.service_type),
        name_ru=data.name_ru,
        name_uz=data.name_uz,
        duration_minutes=data.duration_minutes,
        price=Decimal(str(data.price)),
        sort_order=data.sort_order,
    )
    session.add(svc)
    await session.commit()
    await session.refresh(svc)
    return _service_out(svc)


@router.put("/services/{item_id}", response_model=ServiceOut)
async def update_service(
    item_id: int,
    data: ServiceUpdate,
    session: AsyncSession = Depends(get_session),
    user: dict = Depends(get_current_user),
):
    _require_admin(user)
    result = await session.execute(select(ServiceItem).where(ServiceItem.id == item_id))
    svc = result.scalar_one_or_none()
    if not svc:
        raise HTTPException(status_code=404, detail="Service not found")

    updates = data.model_dump(exclude_none=True)
    if "service_type" in updates:
        updates["service_type"] = ServiceType(updates["service_type"])
    if "price" in updates:
        updates["price"] = Decimal(str(updates["price"]))

    for field, value in updates.items():
        setattr(svc, field, value)

    await session.commit()
    await session.refresh(svc)
    return _service_out(svc)


# ── Minibar CRUD ──────────────────────────────────────────────────


def _minibar_out(m: MinibarItem) -> MinibarOut:
    return MinibarOut(
        id=m.id,
        name_ru=m.name_ru,
        name_uz=m.name_uz,
        price=float(m.price),
        is_active=m.is_active,
        sort_order=m.sort_order,
    )


@router.get("/minibar", response_model=list[MinibarOut])
async def list_minibar(
    session: AsyncSession = Depends(get_session),
    user: dict = Depends(get_current_user),
):
    result = await session.execute(select(MinibarItem).order_by(MinibarItem.sort_order))
    return [_minibar_out(m) for m in result.scalars().all()]


@router.post("/minibar", response_model=MinibarOut)
async def create_minibar(
    data: MinibarCreate,
    session: AsyncSession = Depends(get_session),
    user: dict = Depends(get_current_user),
):
    _require_admin(user)
    item = MinibarItem(
        name_ru=data.name_ru,
        name_uz=data.name_uz,
        price=Decimal(str(data.price)),
        sort_order=data.sort_order,
    )
    session.add(item)
    await session.commit()
    await session.refresh(item)
    return _minibar_out(item)


@router.put("/minibar/{item_id}", response_model=MinibarOut)
async def update_minibar(
    item_id: int,
    data: MinibarUpdate,
    session: AsyncSession = Depends(get_session),
    user: dict = Depends(get_current_user),
):
    _require_admin(user)
    result = await session.execute(select(MinibarItem).where(MinibarItem.id == item_id))
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Minibar item not found")

    updates = data.model_dump(exclude_none=True)
    if "price" in updates:
        updates["price"] = Decimal(str(updates["price"]))

    for field, value in updates.items():
        setattr(item, field, value)

    await session.commit()
    await session.refresh(item)
    return _minibar_out(item)


# ── Staff CRUD ────────────────────────────────────────────────────


def _staff_out(s: StaffMember) -> StaffOut:
    return StaffOut(
        id=s.id,
        name=s.name,
        role_description=s.role_description,
        is_active=s.is_active,
    )


@router.get("/staff", response_model=list[StaffOut])
async def list_staff(
    session: AsyncSession = Depends(get_session),
    user: dict = Depends(get_current_user),
):
    result = await session.execute(select(StaffMember))
    return [_staff_out(s) for s in result.scalars().all()]


@router.post("/staff", response_model=StaffOut)
async def create_staff(
    data: StaffCreate,
    session: AsyncSession = Depends(get_session),
    user: dict = Depends(get_current_user),
):
    _require_admin(user)
    member = StaffMember(
        name=data.name,
        role_description=data.role_description,
    )
    session.add(member)
    await session.commit()
    await session.refresh(member)
    return _staff_out(member)


@router.put("/staff/{item_id}", response_model=StaffOut)
async def update_staff(
    item_id: int,
    data: StaffUpdate,
    session: AsyncSession = Depends(get_session),
    user: dict = Depends(get_current_user),
):
    _require_admin(user)
    result = await session.execute(select(StaffMember).where(StaffMember.id == item_id))
    member = result.scalar_one_or_none()
    if not member:
        raise HTTPException(status_code=404, detail="Staff member not found")

    for field, value in data.model_dump(exclude_none=True).items():
        setattr(member, field, value)

    await session.commit()
    await session.refresh(member)
    return _staff_out(member)
