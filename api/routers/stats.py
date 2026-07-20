"""Statistics hub — surfaces the CRM's request/conversation and bot-usage data inside
analytics, so everything lives behind one login. Analytics and the CRM are separate
services with separate databases, so analytics proxies the CRM over the existing bridge
(shared secret) rather than reading its tables directly."""

from datetime import date, timedelta

import aiohttp
from fastapi import APIRouter, Depends, HTTPException, Query

from api.auth import get_current_user
from bot.config import settings

router = APIRouter()

CRM_BASE = settings.crm_api_url.rstrip("/")


async def _crm_get(path: str) -> dict:
    """GET a CRM endpoint with the shared bridge secret (== CRM INTAKE_SECRET)."""
    if not settings.bridge_secret:
        raise HTTPException(status_code=503, detail="Мост с CRM не настроен (bridge_secret)")
    url = f"{CRM_BASE}{path}"
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(
                url,
                headers={"X-Intake-Secret": settings.bridge_secret},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as r:
                if r.status == 401:
                    raise HTTPException(status_code=502, detail="CRM отклонил секрет (проверьте bridge_secret)")
                if r.status >= 400:
                    raise HTTPException(status_code=502, detail=f"CRM вернул ошибку ({r.status})")
                return await r.json(content_type=None)
    except aiohttp.ClientError as e:
        raise HTTPException(status_code=502, detail="CRM недоступен") from e


def _range(frm: str | None, to: str | None) -> tuple[str, str]:
    today = date.today()
    f = frm or (today - timedelta(days=30)).isoformat()
    t = to or today.isoformat()
    return f, t


@router.get("/overview")
async def overview(
    frm: str | None = Query(None, alias="from"),
    to: str | None = Query(None),
    user: dict = Depends(get_current_user),
):
    """Leads (website/phone/telegram/instagram) + conversation stats + response times."""
    f, t = _range(frm, to)
    return await _crm_get(f"/api/overview?from={f}&to={t}")


@router.get("/bot")
async def bot_stats(
    frm: str | None = Query(None, alias="from"),
    to: str | None = Query(None),
    user: dict = Depends(get_current_user),
):
    """@balandda_bot usage funnel (reached → browsed → requested → submitted)."""
    f, t = _range(frm, to)
    return await _crm_get(f"/api/bot-stats?from={f}&to={t}")
