"""Ad conversions ledger: list, Google/Yandex CSV export, manual scan (owner only)."""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from fastapi.responses import PlainTextResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth import get_current_user, require_owner
from db.database import get_session
from db.models import AdConversion
from services import ad_conversions as ac

router = APIRouter()


async def _rows(session, days: int, event: str | None):
    since = datetime.now(timezone.utc) - timedelta(days=days)
    q = select(AdConversion).where(AdConversion.event_time >= since).order_by(AdConversion.event_time.desc())
    if event:
        q = q.where(AdConversion.event_name == event)
    return (await session.execute(q)).scalars().all()


@router.get("")
async def list_conversions(days: int = Query(30, ge=1, le=400), event: str | None = None,
                           session: AsyncSession = Depends(get_session), user: dict = Depends(get_current_user)):
    require_owner(user)
    rows = await _rows(session, days, event)
    return [{
        "reservation_id": c.reservation_id, "event": c.event_name, "event_id": c.event_id,
        "time": c.event_time.isoformat(), "value": float(c.value or 0), "source": c.source,
        "pay_kind": c.pay_kind, "ad_origin": c.ad_origin, "ads": c.ads, "meta": c.meta_status,
        "meta_response": (c.meta_response or "")[:200],
    } for c in rows]


@router.get("/export")
async def export_csv(network: str = Query(..., pattern="^(google|yandex)$"), event: str = "Purchase",
                     days: int = Query(30, ge=1, le=90),
                     session: AsyncSession = Depends(get_session), user: dict = Depends(get_current_user)):
    require_owner(user)
    rows = await _rows(session, days, event)
    body = ac.google_csv(rows) if network == "google" else ac.yandex_csv(rows)
    fn = f"balandda_{network}_{event.lower()}_{datetime.now().strftime('%Y%m%d')}.csv"
    return PlainTextResponse(body, media_type="text/csv",
                             headers={"Content-Disposition": f'attachment; filename="{fn}"'})


@router.post("/scan")
async def scan_now(user: dict = Depends(get_current_user)):
    require_owner(user)
    return await ac.run_scan()
