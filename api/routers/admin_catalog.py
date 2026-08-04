"""Admin CRUD endpoints for catalog items (properties, services, minibar, staff)."""

from datetime import date
from decimal import Decimal

import re

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from api.auth import get_current_user, require_admin
from db.booking_rules import WINDOW_KEY, get_blocked, get_max_date, get_window_months, today_local
from db.database import get_session
from db.enums import (
    PROPERTY_TYPE_LABELS,
    SERVICE_TYPE_LABELS,
    PropertyType,
    ServiceType,
)
from db.models import (
    AppSetting,
    BlockedPeriod,
    BusinessUnit,
    MinibarItem,
    MinibarSection,
    MINISHOP_SELLER_SETTING_KEY,
    Property,
    PropertyTypeLabel,
    ServiceCategory,
    ServiceItem,
    ServiceTypeDef,
    SpaLocation,
    SpaMaster,
    StaffMember,
    User,
    get_service_type_labels,
)
from services.beds24 import kick as beds24_kick  # re-push OTA availability on rule changes

LOCATION_MODES = {"room_only", "room_or_cottage", "cottage_only"}

router = APIRouter()


def _require_admin(user: dict):
    require_admin(user)


# ── Property schemas ──────────────────────────────────────────────


class PropertyCreate(BaseModel):
    code: str
    name_ru: str
    name_uz: str
    name_en: str | None = None
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
    name_en: str | None = None
    property_type: str | None = None
    unit_number: str | None = None
    capacity: int | None = None
    has_sauna: bool | None = None
    price_weekday: float | None = None
    price_weekend: float | None = None
    emoji: str | None = None
    sort_order: int | None = None
    is_active: bool | None = None
    business_unit: str | None = None


class PropertyOut(BaseModel):
    id: int
    code: str
    name_ru: str
    name_uz: str
    name_en: str | None
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
    category_id: int | None = None
    location_mode: str = "room_or_cottage"
    master_percent: float = 0
    commission_internal: float = 0
    commission_external: float = 0
    master_ids: list[int] = []
    location_ids: list[int] = []


class ServiceUpdate(BaseModel):
    service_type: str | None = None
    name_ru: str | None = None
    name_uz: str | None = None
    duration_minutes: int | None = None
    price: float | None = None
    sort_order: int | None = None
    is_active: bool | None = None
    category_id: int | None = None
    location_mode: str | None = None
    master_percent: float | None = None
    commission_internal: float | None = None
    commission_external: float | None = None
    master_ids: list[int] | None = None
    location_ids: list[int] | None = None


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
    category_id: int | None
    category_name: str | None
    location_mode: str
    master_percent: float
    commission_internal: float
    commission_external: float
    master_ids: list[int]
    location_ids: list[int]


# ── SPA category / location / master schemas ──────────────────────


class CategoryCreate(BaseModel):
    name_ru: str
    name_uz: str
    sort_order: int = 0


class CategoryUpdate(BaseModel):
    name_ru: str | None = None
    name_uz: str | None = None
    sort_order: int | None = None
    is_active: bool | None = None


class CategoryOut(BaseModel):
    id: int
    name_ru: str
    name_uz: str
    is_active: bool
    sort_order: int


class SpaLocationCreate(BaseModel):
    name_ru: str
    name_uz: str
    sort_order: int = 0


class SpaLocationUpdate(BaseModel):
    name_ru: str | None = None
    name_uz: str | None = None
    sort_order: int | None = None
    is_active: bool | None = None


class SpaLocationOut(BaseModel):
    id: int
    name_ru: str
    name_uz: str
    is_active: bool
    sort_order: int


MASTER_TYPES = {"internal", "external"}


class SpaMasterCreate(BaseModel):
    name: str
    phone: str | None = None
    telegram_id: int | None = None
    master_type: str = "internal"
    sort_order: int = 0


class SpaMasterUpdate(BaseModel):
    name: str | None = None
    phone: str | None = None
    telegram_id: int | None = None   # send 0 to clear
    master_type: str | None = None
    sort_order: int | None = None
    is_active: bool | None = None


class SpaMasterOut(BaseModel):
    id: int
    name: str
    phone: str | None
    telegram_id: int | None
    master_type: str
    is_active: bool
    sort_order: int


# ── Minibar schemas ───────────────────────────────────────────────


class MinibarCreate(BaseModel):
    name_ru: str
    name_uz: str
    price: float = 0
    sort_order: int = 0
    section: MinibarSection = MinibarSection.MINIBAR


class MinibarUpdate(BaseModel):
    name_ru: str | None = None
    name_uz: str | None = None
    price: float | None = None
    sort_order: int | None = None
    is_active: bool | None = None
    section: MinibarSection | None = None


class MinibarOut(BaseModel):
    id: int
    name_ru: str
    name_uz: str
    price: float
    is_active: bool
    sort_order: int
    section: MinibarSection


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
async def list_enums(
    session: AsyncSession = Depends(get_session),
    user: dict = Depends(get_current_user),
):
    """Return available enum values for dropdowns."""
    type_rows = (
        await session.execute(
            select(ServiceTypeDef)
            .where(ServiceTypeDef.is_active.is_(True))
            .order_by(ServiceTypeDef.sort_order, ServiceTypeDef.code)
        )
    ).scalars().all()
    service_types = (
        [{"value": r.code, "label": r.label_ru} for r in type_rows]
        if type_rows
        # Fallback for a DB that predates the service_types migration
        else [
            {"value": st.value, "label": SERVICE_TYPE_LABELS.get(st, st.value)}
            for st in ServiceType
        ]
    )
    return {
        "property_types": [
            {"value": pt.value, "label": PROPERTY_TYPE_LABELS.get(pt, pt.value)}
            for pt in PropertyType
        ],
        "service_types": service_types,
        "business_units": [
            {"value": bu.value, "label": bu.value}
            for bu in BusinessUnit
        ],
    }


# ── Type-label CRUD (editable category titles per language) ───────


class TypeLabelOut(BaseModel):
    property_type: str
    label_ru: str
    label_uz: str
    label_en: str | None


class TypeLabelUpdate(BaseModel):
    label_ru: str | None = None
    label_uz: str | None = None
    label_en: str | None = None


@router.get("/type-labels", response_model=list[TypeLabelOut])
async def list_type_labels(
    session: AsyncSession = Depends(get_session),
    user: dict = Depends(get_current_user),
):
    """All editable stay-type labels, one row per PropertyType (falls back to enum defaults)."""
    rows = {r.property_type: r for r in (await session.execute(select(PropertyTypeLabel))).scalars().all()}
    out: list[TypeLabelOut] = []
    for pt in PropertyType:
        r = rows.get(pt.value)
        if r:
            out.append(TypeLabelOut(property_type=pt.value, label_ru=r.label_ru, label_uz=r.label_uz, label_en=r.label_en))
        else:
            ru = PROPERTY_TYPE_LABELS.get(pt, pt.value)
            out.append(TypeLabelOut(property_type=pt.value, label_ru=ru, label_uz=ru, label_en=ru))
    return out


@router.put("/type-labels/{property_type}", response_model=TypeLabelOut)
async def update_type_label(
    property_type: str,
    data: TypeLabelUpdate,
    session: AsyncSession = Depends(get_session),
    user: dict = Depends(get_current_user),
):
    _require_admin(user)
    if property_type not in {pt.value for pt in PropertyType}:
        raise HTTPException(status_code=404, detail="Unknown property type")
    row = (
        await session.execute(select(PropertyTypeLabel).where(PropertyTypeLabel.property_type == property_type))
    ).scalar_one_or_none()
    if not row:
        base = PROPERTY_TYPE_LABELS.get(PropertyType(property_type), property_type)
        row = PropertyTypeLabel(property_type=property_type, label_ru=base, label_uz=base, label_en=base)
        session.add(row)
    for field, value in data.model_dump(exclude_none=True).items():
        setattr(row, field, value)
    await session.commit()
    await session.refresh(row)
    return TypeLabelOut(
        property_type=row.property_type, label_ru=row.label_ru, label_uz=row.label_uz, label_en=row.label_en
    )


# ── Property CRUD ─────────────────────────────────────────────────


def _property_out(p: Property) -> PropertyOut:
    return PropertyOut(
        id=p.id,
        code=p.code,
        name_ru=p.name_ru,
        name_uz=p.name_uz,
        name_en=p.name_en,
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
        name_en=data.name_en,
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
    if "business_unit" in updates:
        updates["business_unit"] = BusinessUnit(updates["business_unit"])

    for field, value in updates.items():
        setattr(prop, field, value)

    await session.commit()
    await session.refresh(prop)
    return _property_out(prop)


# ── Service CRUD ──────────────────────────────────────────────────


_SERVICE_OPTS = (
    selectinload(ServiceItem.category),
    selectinload(ServiceItem.masters),
    selectinload(ServiceItem.allowed_locations),
)


def _service_out(s: ServiceItem, labels: dict[str, str]) -> ServiceOut:
    return ServiceOut(
        id=s.id,
        service_type=s.service_type,
        service_type_label=labels.get(s.service_type, s.service_type),
        name_ru=s.name_ru,
        name_uz=s.name_uz,
        duration_minutes=s.duration_minutes,
        price=float(s.price),
        is_active=s.is_active,
        sort_order=s.sort_order,
        category_id=s.category_id,
        category_name=s.category.name_ru if s.category else None,
        location_mode=s.location_mode or "room_or_cottage",
        master_percent=float(s.master_percent or 0),
        commission_internal=float(s.commission_internal or 0),
        commission_external=float(s.commission_external or 0),
        master_ids=sorted(m.id for m in s.masters),
        location_ids=sorted(loc.id for loc in s.allowed_locations),
    )


async def _load_service(session: AsyncSession, item_id: int) -> ServiceItem | None:
    return (
        await session.execute(
            select(ServiceItem).options(*_SERVICE_OPTS).where(ServiceItem.id == item_id)
        )
    ).scalar_one_or_none()


async def _apply_service_relations(session: AsyncSession, svc: ServiceItem, master_ids, location_ids):
    if master_ids is not None:
        svc.masters = (
            list((await session.execute(select(SpaMaster).where(SpaMaster.id.in_(master_ids)))).scalars().all())
            if master_ids else []
        )
    if location_ids is not None:
        svc.allowed_locations = (
            list((await session.execute(select(SpaLocation).where(SpaLocation.id.in_(location_ids)))).scalars().all())
            if location_ids else []
        )


@router.get("/services", response_model=list[ServiceOut])
async def list_services(
    session: AsyncSession = Depends(get_session),
    user: dict = Depends(get_current_user),
):
    result = await session.execute(
        select(ServiceItem).options(*_SERVICE_OPTS).order_by(ServiceItem.sort_order)
    )
    labels = await get_service_type_labels(session)
    return [_service_out(s, labels) for s in result.scalars().all()]


@router.post("/services", response_model=ServiceOut)
async def create_service(
    data: ServiceCreate,
    session: AsyncSession = Depends(get_session),
    user: dict = Depends(get_current_user),
):
    _require_admin(user)
    if data.location_mode not in LOCATION_MODES:
        raise HTTPException(status_code=422, detail="Invalid location_mode")
    if not data.service_type:
        raise HTTPException(status_code=422, detail="Выберите тип услуги")
    labels = await get_service_type_labels(session)
    if data.service_type not in labels:
        raise HTTPException(status_code=422, detail="Неизвестный тип услуги")
    # NOTE: relations are fetched up-front and passed to the constructor.
    # Assigning svc.masters/allowed_locations AFTER flush() lazy-loads the old
    # collection, which raises MissingGreenlet under the async engine (this is
    # what made every "add service" request fail with a 500).
    masters = (
        list((await session.execute(select(SpaMaster).where(SpaMaster.id.in_(data.master_ids)))).scalars().all())
        if data.master_ids else []
    )
    locations = (
        list((await session.execute(select(SpaLocation).where(SpaLocation.id.in_(data.location_ids)))).scalars().all())
        if data.location_ids else []
    )
    svc = ServiceItem(
        service_type=data.service_type,
        name_ru=data.name_ru,
        name_uz=data.name_uz,
        duration_minutes=data.duration_minutes,
        price=Decimal(str(data.price)),
        sort_order=data.sort_order,
        category_id=data.category_id,
        location_mode=data.location_mode,
        master_percent=Decimal(str(data.master_percent)),
        commission_internal=Decimal(str(data.commission_internal)),
        commission_external=Decimal(str(data.commission_external)),
        masters=masters,
        allowed_locations=locations,
    )
    session.add(svc)
    await session.commit()
    return _service_out(await _load_service(session, svc.id), labels)


@router.put("/services/{item_id}", response_model=ServiceOut)
async def update_service(
    item_id: int,
    data: ServiceUpdate,
    session: AsyncSession = Depends(get_session),
    user: dict = Depends(get_current_user),
):
    _require_admin(user)
    svc = await _load_service(session, item_id)
    if not svc:
        raise HTTPException(status_code=404, detail="Service not found")

    updates = data.model_dump(exclude_none=True)
    master_ids = updates.pop("master_ids", None)
    location_ids = updates.pop("location_ids", None)
    labels = await get_service_type_labels(session)
    if "service_type" in updates and updates["service_type"] not in labels:
        raise HTTPException(status_code=422, detail="Неизвестный тип услуги")
    if "price" in updates:
        updates["price"] = Decimal(str(updates["price"]))
    if "master_percent" in updates:
        updates["master_percent"] = Decimal(str(updates["master_percent"]))
    for _cf in ("commission_internal", "commission_external"):
        if _cf in updates:
            updates[_cf] = Decimal(str(updates[_cf]))
    if "location_mode" in updates and updates["location_mode"] not in LOCATION_MODES:
        raise HTTPException(status_code=422, detail="Invalid location_mode")

    for field, value in updates.items():
        setattr(svc, field, value)
    await _apply_service_relations(session, svc, master_ids, location_ids)

    await session.commit()
    return _service_out(await _load_service(session, item_id), labels)


# ── Service type CRUD (editable «Тип» dropdown) ───────────────────


class ServiceTypeCreate(BaseModel):
    label_ru: str
    label_uz: str = ""
    code: str | None = None
    sort_order: int = 0


class ServiceTypeUpdate(BaseModel):
    label_ru: str | None = None
    label_uz: str | None = None
    sort_order: int | None = None
    is_active: bool | None = None


class ServiceTypeOut(BaseModel):
    code: str
    label_ru: str
    label_uz: str
    is_active: bool
    sort_order: int
    services_count: int


_TRANSLIT = {
    "а": "A", "б": "B", "в": "V", "г": "G", "д": "D", "е": "E", "ё": "E",
    "ж": "ZH", "з": "Z", "и": "I", "й": "Y", "к": "K", "л": "L", "м": "M",
    "н": "N", "о": "O", "п": "P", "р": "R", "с": "S", "т": "T", "у": "U",
    "ф": "F", "х": "KH", "ц": "TS", "ч": "CH", "ш": "SH", "щ": "SCH",
    "ъ": "", "ы": "Y", "ь": "", "э": "E", "ю": "YU", "я": "YA",
    "ў": "O", "қ": "Q", "ғ": "G", "ҳ": "H",
}


def _slug_code(label: str) -> str:
    out = "".join(_TRANSLIT.get(ch, ch) for ch in label.lower())
    out = re.sub(r"[^A-Za-z0-9]+", "_", out.upper()).strip("_")
    return out[:32] or "TYPE"


async def _service_type_counts(session: AsyncSession) -> dict[str, int]:
    rows = (
        await session.execute(
            select(ServiceItem.service_type, func.count(ServiceItem.id))
            .group_by(ServiceItem.service_type)
        )
    ).all()
    return {code: cnt for code, cnt in rows}


def _type_out(t: ServiceTypeDef, counts: dict[str, int]) -> ServiceTypeOut:
    return ServiceTypeOut(
        code=t.code, label_ru=t.label_ru, label_uz=t.label_uz,
        is_active=t.is_active, sort_order=t.sort_order,
        services_count=counts.get(t.code, 0),
    )


@router.get("/service-types", response_model=list[ServiceTypeOut])
async def list_service_types(
    session: AsyncSession = Depends(get_session),
    user: dict = Depends(get_current_user),
):
    rows = (
        await session.execute(
            select(ServiceTypeDef).order_by(ServiceTypeDef.sort_order, ServiceTypeDef.code)
        )
    ).scalars().all()
    counts = await _service_type_counts(session)
    return [_type_out(t, counts) for t in rows]


@router.post("/service-types", response_model=ServiceTypeOut)
async def create_service_type(
    data: ServiceTypeCreate,
    session: AsyncSession = Depends(get_session),
    user: dict = Depends(get_current_user),
):
    _require_admin(user)
    label_ru = data.label_ru.strip()
    if not label_ru:
        raise HTTPException(status_code=422, detail="Укажите название типа (RU)")
    existing = {
        c for (c,) in (await session.execute(select(ServiceTypeDef.code))).all()
    }
    code = (data.code or "").strip().upper() or _slug_code(label_ru)
    code = re.sub(r"[^A-Z0-9_]+", "_", code).strip("_")[:36] or "TYPE"
    base, n = code, 2
    while code in existing:
        code = f"{base}_{n}"
        n += 1
    t = ServiceTypeDef(
        code=code,
        label_ru=label_ru,
        label_uz=data.label_uz.strip() or label_ru,
        sort_order=data.sort_order,
    )
    session.add(t)
    await session.commit()
    await session.refresh(t)
    return _type_out(t, await _service_type_counts(session))


@router.put("/service-types/{code}", response_model=ServiceTypeOut)
async def update_service_type(
    code: str,
    data: ServiceTypeUpdate,
    session: AsyncSession = Depends(get_session),
    user: dict = Depends(get_current_user),
):
    _require_admin(user)
    t = (
        await session.execute(select(ServiceTypeDef).where(ServiceTypeDef.code == code))
    ).scalar_one_or_none()
    if not t:
        raise HTTPException(status_code=404, detail="Тип не найден")
    for field, value in data.model_dump(exclude_none=True).items():
        setattr(t, field, value)
    await session.commit()
    await session.refresh(t)
    return _type_out(t, await _service_type_counts(session))


@router.delete("/service-types/{code}")
async def delete_service_type(
    code: str,
    session: AsyncSession = Depends(get_session),
    user: dict = Depends(get_current_user),
):
    _require_admin(user)
    t = (
        await session.execute(select(ServiceTypeDef).where(ServiceTypeDef.code == code))
    ).scalar_one_or_none()
    if not t:
        raise HTTPException(status_code=404, detail="Тип не найден")
    counts = await _service_type_counts(session)
    if counts.get(code):
        raise HTTPException(
            status_code=409,
            detail=f"Тип используется в {counts[code]} услуг(ах) — сначала переведите их на другой тип или выключите тип.",
        )
    await session.delete(t)
    await session.commit()
    return {"ok": True}


# ── SPA Category CRUD ─────────────────────────────────────────────


def _category_out(c: ServiceCategory) -> CategoryOut:
    return CategoryOut(id=c.id, name_ru=c.name_ru, name_uz=c.name_uz, is_active=c.is_active, sort_order=c.sort_order)


@router.get("/service-categories", response_model=list[CategoryOut])
async def list_categories(
    session: AsyncSession = Depends(get_session),
    user: dict = Depends(get_current_user),
):
    result = await session.execute(select(ServiceCategory).order_by(ServiceCategory.sort_order))
    return [_category_out(c) for c in result.scalars().all()]


@router.post("/service-categories", response_model=CategoryOut)
async def create_category(
    data: CategoryCreate,
    session: AsyncSession = Depends(get_session),
    user: dict = Depends(get_current_user),
):
    _require_admin(user)
    c = ServiceCategory(name_ru=data.name_ru, name_uz=data.name_uz, sort_order=data.sort_order)
    session.add(c)
    await session.commit()
    await session.refresh(c)
    return _category_out(c)


@router.put("/service-categories/{item_id}", response_model=CategoryOut)
async def update_category(
    item_id: int,
    data: CategoryUpdate,
    session: AsyncSession = Depends(get_session),
    user: dict = Depends(get_current_user),
):
    _require_admin(user)
    c = (await session.execute(select(ServiceCategory).where(ServiceCategory.id == item_id))).scalar_one_or_none()
    if not c:
        raise HTTPException(status_code=404, detail="Category not found")
    for field, value in data.model_dump(exclude_none=True).items():
        setattr(c, field, value)
    await session.commit()
    await session.refresh(c)
    return _category_out(c)


# ── SPA Location CRUD ─────────────────────────────────────────────


def _location_out(l: SpaLocation) -> SpaLocationOut:
    return SpaLocationOut(id=l.id, name_ru=l.name_ru, name_uz=l.name_uz, is_active=l.is_active, sort_order=l.sort_order)


@router.get("/spa-locations", response_model=list[SpaLocationOut])
async def list_spa_locations(
    session: AsyncSession = Depends(get_session),
    user: dict = Depends(get_current_user),
):
    result = await session.execute(select(SpaLocation).order_by(SpaLocation.sort_order))
    return [_location_out(l) for l in result.scalars().all()]


@router.post("/spa-locations", response_model=SpaLocationOut)
async def create_spa_location(
    data: SpaLocationCreate,
    session: AsyncSession = Depends(get_session),
    user: dict = Depends(get_current_user),
):
    _require_admin(user)
    l = SpaLocation(name_ru=data.name_ru, name_uz=data.name_uz, sort_order=data.sort_order)
    session.add(l)
    await session.commit()
    await session.refresh(l)
    return _location_out(l)


@router.put("/spa-locations/{item_id}", response_model=SpaLocationOut)
async def update_spa_location(
    item_id: int,
    data: SpaLocationUpdate,
    session: AsyncSession = Depends(get_session),
    user: dict = Depends(get_current_user),
):
    _require_admin(user)
    l = (await session.execute(select(SpaLocation).where(SpaLocation.id == item_id))).scalar_one_or_none()
    if not l:
        raise HTTPException(status_code=404, detail="Location not found")
    for field, value in data.model_dump(exclude_none=True).items():
        setattr(l, field, value)
    await session.commit()
    await session.refresh(l)
    return _location_out(l)


# ── SPA Master CRUD ───────────────────────────────────────────────


def _master_out(m: SpaMaster) -> SpaMasterOut:
    return SpaMasterOut(
        id=m.id, name=m.name, phone=m.phone,
        telegram_id=m.telegram_id, master_type=m.master_type or "internal",
        is_active=m.is_active, sort_order=m.sort_order,
    )


@router.get("/spa-masters", response_model=list[SpaMasterOut])
async def list_spa_masters(
    session: AsyncSession = Depends(get_session),
    user: dict = Depends(get_current_user),
):
    result = await session.execute(select(SpaMaster).order_by(SpaMaster.sort_order))
    return [_master_out(m) for m in result.scalars().all()]


@router.post("/spa-masters", response_model=SpaMasterOut)
async def create_spa_master(
    data: SpaMasterCreate,
    session: AsyncSession = Depends(get_session),
    user: dict = Depends(get_current_user),
):
    _require_admin(user)
    if data.master_type not in MASTER_TYPES:
        raise HTTPException(status_code=422, detail="Invalid master_type")
    m = SpaMaster(
        name=data.name, phone=data.phone,
        telegram_id=data.telegram_id or None, master_type=data.master_type,
        sort_order=data.sort_order,
    )
    session.add(m)
    await session.commit()
    await session.refresh(m)
    return _master_out(m)


@router.put("/spa-masters/{item_id}", response_model=SpaMasterOut)
async def update_spa_master(
    item_id: int,
    data: SpaMasterUpdate,
    session: AsyncSession = Depends(get_session),
    user: dict = Depends(get_current_user),
):
    _require_admin(user)
    m = (await session.execute(select(SpaMaster).where(SpaMaster.id == item_id))).scalar_one_or_none()
    if not m:
        raise HTTPException(status_code=404, detail="Master not found")
    updates = data.model_dump(exclude_none=True)
    if "master_type" in updates and updates["master_type"] not in MASTER_TYPES:
        raise HTTPException(status_code=422, detail="Invalid master_type")
    if updates.get("telegram_id") == 0:
        updates["telegram_id"] = None
    for field, value in updates.items():
        setattr(m, field, value)
    await session.commit()
    await session.refresh(m)
    return _master_out(m)


# ── Minibar CRUD ──────────────────────────────────────────────────


def _minibar_out(m: MinibarItem) -> MinibarOut:
    return MinibarOut(
        id=m.id,
        name_ru=m.name_ru,
        name_uz=m.name_uz,
        price=float(m.price),
        is_active=m.is_active,
        sort_order=m.sort_order,
        section=m.section or MinibarSection.MINIBAR,
    )


@router.get("/minibar", response_model=list[MinibarOut])
async def list_minibar(
    section: MinibarSection | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
    user: dict = Depends(get_current_user),
):
    query = select(MinibarItem).order_by(MinibarItem.sort_order)
    if section is not None:
        query = query.where(MinibarItem.section == section)
    result = await session.execute(query)
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
        section=data.section,
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


# ── Mini shop seller ──────────────────────────────────────────────
#
# Mini shop is cash-only and the cash always belongs to one person (the shop
# seller), whoever happens to type the sale into the bot. That telegram_id lives
# in app_settings; the bot reads it in new_report.on_minishop_confirm.


class MinishopSellerUpdate(BaseModel):
    telegram_id: int | None = None  # null clears it → cash falls back to the recorder


@router.get("/minishop/seller")
async def get_minishop_seller(
    session: AsyncSession = Depends(get_session),
    user: dict = Depends(get_current_user),
):
    row = await session.get(AppSetting, MINISHOP_SELLER_SETTING_KEY)
    raw = (row.value or "").strip() if row else ""
    if not raw:
        return {"telegram_id": None, "full_name": None}

    try:
        tid = int(raw)
    except ValueError:
        return {"telegram_id": None, "full_name": None}

    result = await session.execute(select(User).where(User.telegram_id == tid))
    seller = result.scalar_one_or_none()
    return {"telegram_id": tid, "full_name": seller.full_name if seller else None}


@router.put("/minishop/seller")
async def set_minishop_seller(
    data: MinishopSellerUpdate,
    session: AsyncSession = Depends(get_session),
    user: dict = Depends(get_current_user),
):
    _require_admin(user)
    value = "" if data.telegram_id is None else str(data.telegram_id)

    if value:
        result = await session.execute(select(User).where(User.telegram_id == data.telegram_id))
        if not result.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="No user with that telegram_id")

    row = await session.get(AppSetting, MINISHOP_SELLER_SETTING_KEY)
    if row:
        row.value = value
    else:
        session.add(AppSetting(key=MINISHOP_SELLER_SETTING_KEY, value=value))
    await session.commit()
    return await get_minishop_seller(session, user)


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


# ── Booking rules: sales window + blocked (closed) dates ──────────
# Window: bookings open only `today + N months` ahead (rolling, default 9).
# Blocks: resort-wide (property_id null) or per-unit; nights date_from..date_to
# inclusive are unsellable. Both are enforced in public availability + bridge
# bookings and pushed to OTAs (Beds24 numAvail=0) — beds24_kick() re-syncs.


class WindowUpdate(BaseModel):
    months: int


class BlockedCreate(BaseModel):
    date_from: date
    date_to: date
    property_id: int | None = None  # null = whole resort
    reason: str | None = None


class BlockedOut(BaseModel):
    id: int
    date_from: date
    date_to: date
    property_id: int | None
    unit_name: str | None
    unit_code: str | None
    reason: str | None


async def _blocked_out(session: AsyncSession, b: BlockedPeriod) -> BlockedOut:
    prop = await session.get(Property, b.property_id) if b.property_id else None
    return BlockedOut(
        id=b.id, date_from=b.date_from, date_to=b.date_to, property_id=b.property_id,
        unit_name=(prop.name_ru if prop else None), unit_code=(prop.code if prop else None),
        reason=b.reason,
    )


@router.get("/booking-rules")
async def admin_booking_rules(
    session: AsyncSession = Depends(get_session),
    user: dict = Depends(get_current_user),
):
    months = await get_window_months(session)
    blocked = [await _blocked_out(session, b) for b in await get_blocked(session, include_past=True)]
    blocked.sort(key=lambda b: b.date_from, reverse=True)
    return {
        "window_months": months,
        "max_date": (await get_max_date(session)).isoformat(),
        "today": today_local().isoformat(),
        "blocked": blocked,
    }


@router.put("/booking-rules/window")
async def set_booking_window(
    data: WindowUpdate,
    session: AsyncSession = Depends(get_session),
    user: dict = Depends(get_current_user),
):
    _require_admin(user)
    if not 1 <= data.months <= 24:
        raise HTTPException(status_code=400, detail="months must be between 1 and 24")
    row = await session.get(AppSetting, WINDOW_KEY)
    if row:
        row.value = str(data.months)
    else:
        session.add(AppSetting(key=WINDOW_KEY, value=str(data.months)))
    await session.commit()
    beds24_kick()  # close/open the tail of the OTA calendar
    return {"window_months": data.months, "max_date": (await get_max_date(session)).isoformat()}


@router.post("/blocked-dates", response_model=BlockedOut)
async def create_blocked_period(
    data: BlockedCreate,
    session: AsyncSession = Depends(get_session),
    user: dict = Depends(get_current_user),
):
    _require_admin(user)
    if data.date_to < data.date_from:
        raise HTTPException(status_code=400, detail="date_to must be >= date_from")
    if data.property_id is not None and not await session.get(Property, data.property_id):
        raise HTTPException(status_code=404, detail="Unit not found")
    b = BlockedPeriod(
        date_from=data.date_from, date_to=data.date_to,
        property_id=data.property_id,
        reason=(data.reason or "").strip()[:200] or None,
        created_by=user.get("telegram_id"),
    )
    session.add(b)
    await session.commit()
    await session.refresh(b)
    beds24_kick()  # zero these dates on the OTAs
    return await _blocked_out(session, b)


@router.delete("/blocked-dates/{item_id}")
async def delete_blocked_period(
    item_id: int,
    session: AsyncSession = Depends(get_session),
    user: dict = Depends(get_current_user),
):
    _require_admin(user)
    b = await session.get(BlockedPeriod, item_id)
    if not b:
        raise HTTPException(status_code=404, detail="Not found")
    await session.delete(b)
    await session.commit()
    beds24_kick()  # reopen the dates on the OTAs
    return {"ok": True}
