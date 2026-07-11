"""Unified bot content — one set of reply templates rendered on BOTH Telegram and Instagram.

Admin edits them in analytics; the CRM fetches the rendered tree from the public endpoint,
so the two channels can never drift apart. Price blocks are rendered from the live catalog
at request time, which means prices in the bot always match the calendar.
"""

import json
import os
import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from api.auth import get_current_user, require_admin
from db.database import get_session
from db.models import BotTemplate, BusinessUnit, Property, ServiceItem

router = APIRouter()

UPLOAD_DIR = "/app/uploads/bot"
PUBLIC_BASE = "https://analytics.berdiev.uz/api/v1/public/bot-image/"
ACTIONS = {"reply", "submenu", "book", "agent"}
PRICE_BLOCKS = {"none", "houses", "pool", "spa"}
LANGS = ("ru", "uz", "en")


# ── Schemas ───────────────────────────────────────────────────────


class TemplateIn(BaseModel):
    parent_id: int | None = None
    key: str | None = None
    action: str = "reply"
    label_ru: str = ""
    label_uz: str = ""
    label_en: str = ""
    ig_label_ru: str | None = None
    ig_label_uz: str | None = None
    ig_label_en: str | None = None
    body_ru: str | None = None
    body_uz: str | None = None
    body_en: str | None = None
    images: list[str] = []
    price_block: str = "none"
    sort_order: int = 0
    is_active: bool = True


class TemplateOut(BaseModel):
    id: int
    parent_id: int | None
    key: str
    action: str
    label_ru: str
    label_uz: str
    label_en: str
    ig_label_ru: str | None
    ig_label_uz: str | None
    ig_label_en: str | None
    body_ru: str | None
    body_uz: str | None
    body_en: str | None
    images: list[str]
    price_block: str
    sort_order: int
    is_active: bool


def _imgs(t: BotTemplate) -> list[str]:
    try:
        v = json.loads(t.images) if t.images else []
        return v if isinstance(v, list) else []
    except Exception:
        return []


def _out(t: BotTemplate) -> TemplateOut:
    return TemplateOut(
        id=t.id, parent_id=t.parent_id, key=t.key, action=t.action,
        label_ru=t.label_ru, label_uz=t.label_uz, label_en=t.label_en,
        ig_label_ru=t.ig_label_ru, ig_label_uz=t.ig_label_uz, ig_label_en=t.ig_label_en,
        body_ru=t.body_ru, body_uz=t.body_uz, body_en=t.body_en,
        images=_imgs(t), price_block=t.price_block or "none",
        sort_order=t.sort_order, is_active=t.is_active,
    )


# ── Admin CRUD ────────────────────────────────────────────────────


@router.get("/bot-templates", response_model=list[TemplateOut])
async def list_templates(
    session: AsyncSession = Depends(get_session),
    user: dict = Depends(get_current_user),
):
    rows = (
        await session.execute(select(BotTemplate).order_by(BotTemplate.parent_id.nulls_first(), BotTemplate.sort_order))
    ).scalars().all()
    return [_out(t) for t in rows]


@router.post("/bot-templates", response_model=TemplateOut)
async def create_template(
    data: TemplateIn,
    session: AsyncSession = Depends(get_session),
    user: dict = Depends(get_current_user),
):
    require_admin(user)
    if data.action not in ACTIONS:
        raise HTTPException(status_code=422, detail="Invalid action")
    if data.price_block not in PRICE_BLOCKS:
        raise HTTPException(status_code=422, detail="Invalid price_block")
    t = BotTemplate(
        parent_id=data.parent_id,
        key=(data.key or f"b{uuid.uuid4().hex[:8]}"),
        action=data.action,
        label_ru=data.label_ru, label_uz=data.label_uz, label_en=data.label_en,
        ig_label_ru=data.ig_label_ru, ig_label_uz=data.ig_label_uz, ig_label_en=data.ig_label_en,
        body_ru=data.body_ru, body_uz=data.body_uz, body_en=data.body_en,
        images=json.dumps(data.images, ensure_ascii=False),
        price_block=data.price_block,
        sort_order=data.sort_order, is_active=data.is_active,
    )
    session.add(t)
    await session.commit()
    await session.refresh(t)
    return _out(t)


@router.put("/bot-templates/{item_id}", response_model=TemplateOut)
async def update_template(
    item_id: int,
    data: TemplateIn,
    session: AsyncSession = Depends(get_session),
    user: dict = Depends(get_current_user),
):
    require_admin(user)
    t = (await session.execute(select(BotTemplate).where(BotTemplate.id == item_id))).scalar_one_or_none()
    if not t:
        raise HTTPException(status_code=404, detail="Template not found")
    if data.action not in ACTIONS:
        raise HTTPException(status_code=422, detail="Invalid action")
    if data.price_block not in PRICE_BLOCKS:
        raise HTTPException(status_code=422, detail="Invalid price_block")

    for f in ("parent_id", "action", "label_ru", "label_uz", "label_en",
              "ig_label_ru", "ig_label_uz", "ig_label_en",
              "body_ru", "body_uz", "body_en", "price_block", "sort_order", "is_active"):
        setattr(t, f, getattr(data, f))
    if data.key:
        t.key = data.key
    t.images = json.dumps(data.images, ensure_ascii=False)

    await session.commit()
    await session.refresh(t)
    return _out(t)


@router.delete("/bot-templates/{item_id}")
async def delete_template(
    item_id: int,
    session: AsyncSession = Depends(get_session),
    user: dict = Depends(get_current_user),
):
    require_admin(user)
    t = (
        await session.execute(
            select(BotTemplate).options(selectinload(BotTemplate.children)).where(BotTemplate.id == item_id)
        )
    ).scalar_one_or_none()
    if not t:
        raise HTTPException(status_code=404, detail="Template not found")
    await session.delete(t)   # children cascade
    await session.commit()
    return {"ok": True}


@router.post("/bot-templates/upload")
async def upload_image(
    file: UploadFile = File(...),
    user: dict = Depends(get_current_user),
):
    """Store an image and return its PUBLIC url — Meta fetches Instagram images unauthenticated."""
    require_admin(user)
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in (".jpg", ".jpeg", ".png", ".webp"):
        raise HTTPException(status_code=422, detail="Только JPG, PNG или WEBP")
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    name = f"{uuid.uuid4().hex}{ext}"
    path = os.path.join(UPLOAD_DIR, name)
    data = await file.read()
    if len(data) > 8 * 1024 * 1024:
        raise HTTPException(status_code=422, detail="Файл больше 8 МБ")
    with open(path, "wb") as fh:
        fh.write(data)
    return {"url": PUBLIC_BASE + name}


# ── Live price blocks ─────────────────────────────────────────────


def _i(v) -> int:
    try:
        return int(float(v or 0))
    except Exception:
        return 0


def _money(n: int) -> str:
    return f"{n:,}".replace(",", " ")


async def _price_text(session: AsyncSession, block: str, lang: str) -> str:
    """Render a live price table from the catalog so the bot never quotes a stale number."""
    if block == "houses":
        rows = (
            await session.execute(
                select(Property).where(
                    Property.is_active.is_(True), Property.business_unit == BusinessUnit.RESORT
                ).order_by(Property.sort_order)
            )
        ).scalars().all()
        by_type: dict[str, tuple[int, int]] = {}
        for p in rows:
            name = {"ru": p.name_ru, "uz": p.name_uz, "en": p.name_en or p.name_ru}.get(lang) or p.name_ru
            wd, we = _i(p.price_weekday), _i(p.price_weekend)
            cur = by_type.get(name)
            by_type[name] = (min(cur[0], wd), min(cur[1], we)) if cur else (wd, we)
        head = {"ru": "💰 Цены за ночь:", "uz": "💰 Bir kecha narxi:", "en": "💰 Price per night:"}[lang]
        lines = [
            f"• {n} — {_money(wd)} / {_money(we)} сум"
            for n, (wd, we) in by_type.items() if wd or we
        ]
        note = {
            "ru": "(будни / суббота и праздники)",
            "uz": "(ish kunlari / shanba va bayramlar)",
            "en": "(weekdays / Saturday & holidays)",
        }[lang]
        return "\n".join([head, *lines, note]) if lines else ""

    if block == "pool":
        rows = (
            await session.execute(
                select(Property).where(
                    Property.is_active.is_(True), Property.business_unit == BusinessUnit.RESTAURANT
                ).order_by(Property.sort_order)
            )
        ).scalars().all()
        head = {"ru": "🏊 Бассейн:", "uz": "🏊 Basseyn:", "en": "🏊 Pool:"}[lang]
        lines = [
            f"• {(p.name_ru if lang == 'ru' else (p.name_uz if lang == 'uz' else (p.name_en or p.name_ru)))}"
            f" — {_money(_i(p.price_weekday))} / {_money(_i(p.price_weekend))} сум"
            for p in rows
        ]
        return "\n".join([head, *lines]) if lines else ""

    if block == "spa":
        rows = (
            await session.execute(
                select(ServiceItem).where(ServiceItem.is_active.is_(True)).order_by(ServiceItem.sort_order)
            )
        ).scalars().all()
        head = {"ru": "💆 SPA:", "uz": "💆 SPA:", "en": "💆 SPA:"}[lang]
        lines = [
            f"• {(s.name_ru if lang != 'uz' else s.name_uz)} — {s.duration_minutes} мин — {_money(_i(s.price))} сум"
            for s in rows
        ]
        return "\n".join([head, *lines]) if lines else ""

    return ""


# ── Public: the rendered flow the CRM feeds to Telegram + Instagram ──


@router.get("/bot-flow")
async def bot_flow(
    response: Response,
    session: AsyncSession = Depends(get_session),
):
    """Public (no auth): the whole bot menu with text already rendered per language,
    live prices injected. The CRM caches this and renders it on both channels."""
    rows = (
        await session.execute(select(BotTemplate).where(BotTemplate.is_active.is_(True)).order_by(BotTemplate.sort_order))
    ).scalars().all()

    # Render each price block once per language rather than per row.
    cache: dict[tuple[str, str], str] = {}

    async def price(block: str, lang: str) -> str:
        if block == "none":
            return ""
        k = (block, lang)
        if k not in cache:
            cache[k] = await _price_text(session, block, lang)
        return cache[k]

    nodes = []
    for t in rows:
        body: dict[str, str] = {}
        label: dict[str, str] = {}
        ig_label: dict[str, str] = {}
        for lang in LANGS:
            raw = (getattr(t, f"body_{lang}") or getattr(t, "body_ru") or "").strip()
            blk = await price(t.price_block or "none", lang)
            body[lang] = (raw + ("\n\n" + blk if blk else "")).strip()
            lbl = (getattr(t, f"label_{lang}") or t.label_ru or "").strip()
            label[lang] = lbl
            ig = (getattr(t, f"ig_label_{lang}") or "").strip() or lbl[:20]
            ig_label[lang] = ig[:20]
        nodes.append({
            "id": t.id,
            "parent_id": t.parent_id,
            "key": t.key,
            "action": t.action,
            "label": label,
            "ig_label": ig_label,
            "body": body,
            "images": _imgs(t),
            "sort_order": t.sort_order,
        })

    response.headers["Cache-Control"] = "public, max-age=60"
    return {"nodes": nodes}


@router.get("/bot-image/{name}")
async def bot_image(name: str):
    """Public image serving — Instagram (Meta) fetches these URLs without any auth header."""
    safe = os.path.basename(name)
    path = os.path.join(UPLOAD_DIR, safe)
    if not os.path.isfile(path):
        raise HTTPException(status_code=404, detail="Not found")
    return FileResponse(path, headers={"Cache-Control": "public, max-age=86400"})
