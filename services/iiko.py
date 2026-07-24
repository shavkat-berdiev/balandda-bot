"""iikoServer (RMS) reports client — restaurant revenue by payment type.

Uses the iikoServer API (https://<name>.iiko.it/resto or self-hosted):
  - GET  /resto/api/auth?login=..&pass=sha1(password)  → session token (plain text)
  - POST /resto/api/v2/reports/olap?key=<token>        → OLAP report (JSON)
  - GET  /resto/api/logout?key=<token>                 → release the license slot

IMPORTANT: iikoServer licenses API sessions — always logout after each pull,
otherwise back-office users can get locked out of a license slot.

Configuration (.env):
  IIKO_SERVER_URL=https://balandda.iiko.it   (base, without /resto)
  IIKO_SERVER_LOGIN=api_user
  IIKO_SERVER_PASSWORD=plain_password        (hashed with sha1 before sending)

Not to be confused with iikoCloud (api-ru.iiko.services) used by the menu
project — the Cloud transport API cannot list all closed POS cheques.
"""

import hashlib
import logging
import time
from datetime import date, timedelta
from decimal import Decimal

import httpx

from bot.config import settings

logger = logging.getLogger(__name__)

_CACHE_TTL = 300  # seconds — dashboard endpoint cache
_cache: dict[tuple[str, str], tuple[float, list]] = {}


def is_configured() -> bool:
    return bool(settings.iiko_server_url and settings.iiko_server_login and settings.iiko_server_password)


def _base() -> str:
    url = settings.iiko_server_url.rstrip("/")
    if url.endswith("/resto"):
        url = url[: -len("/resto")]
    return url


class IikoServerClient:
    """Login → OLAP query → logout, per pull (license-slot friendly)."""

    def __init__(self):
        self.base = _base()

    async def _login(self, client: httpx.AsyncClient) -> str:
        pass_hash = hashlib.sha1(settings.iiko_server_password.encode()).hexdigest()
        resp = await client.get(
            f"{self.base}/resto/api/auth",
            params={"login": settings.iiko_server_login, "pass": pass_hash},
        )
        resp.raise_for_status()
        token = resp.text.strip().strip('"')
        if not token or " " in token:
            raise ValueError(f"iiko auth: unexpected token response: {resp.text[:100]}")
        return token

    async def _logout(self, client: httpx.AsyncClient, token: str) -> None:
        try:
            await client.get(f"{self.base}/resto/api/logout", params={"key": token})
        except Exception as e:
            logger.warning(f"iiko logout failed (license slot may stay busy ~15min): {e}")

    async def sales_by_paytype(self, date_from: date, date_to: date) -> list[dict]:
        """Revenue rows for [date_from; date_to] inclusive.

        Returns [{"date": "YYYY-MM-DD", "pay_type": str, "amount": float}, ...]
        """
        body = {
            "reportType": "SALES",
            "buildSummary": "false",
            "groupByRowFields": ["OpenDate.Typed", "PayTypes"],
            "aggregateFields": ["DishDiscountSumInt"],
            "filters": {
                "OpenDate.Typed": {
                    "filterType": "DateRange",
                    "periodType": "CUSTOM",
                    "from": date_from.isoformat(),
                    "to": (date_to + timedelta(days=1)).isoformat(),
                    "includeLow": True,
                    "includeHigh": False,
                },
                "OrderDeleted": {"filterType": "IncludeValues", "values": ["NOT_DELETED"]},
                "DeletedWithWriteoff": {"filterType": "IncludeValues", "values": ["NOT_DELETED"]},
            },
        }

        async with httpx.AsyncClient(timeout=60) as client:
            token = await self._login(client)
            try:
                resp = await client.post(
                    f"{self.base}/resto/api/v2/reports/olap",
                    params={"key": token},
                    json=body,
                )
                resp.raise_for_status()
                data = resp.json()
            finally:
                await self._logout(client, token)

        rows = data.get("data") if isinstance(data, dict) else data
        result = []
        for row in rows or []:
            day = str(row.get("OpenDate.Typed") or row.get("OpenDate") or "")[:10]
            pay_type = row.get("PayTypes") or "Прочее"
            amount = float(row.get("DishDiscountSumInt") or 0)
            if not day:
                continue
            result.append({"date": day, "pay_type": str(pay_type), "amount": amount})
        return result


async def get_daily_summary(target: date) -> dict | None:
    """One day's revenue split by payment type; None if not configured.

    Returns {"by_paytype": [(name, amount), ...], "total": float} or {"error": str}.
    """
    if not is_configured():
        return None
    try:
        client = IikoServerClient()
        rows = await client.sales_by_paytype(target, target)
    except Exception as e:
        logger.warning(f"iiko daily summary for {target} failed: {e}")
        return {"error": str(e)}

    totals: dict[str, Decimal] = {}
    for r in rows:
        totals[r["pay_type"]] = totals.get(r["pay_type"], Decimal(0)) + Decimal(str(r["amount"]))

    by_paytype = sorted(((k, float(v)) for k, v in totals.items()), key=lambda x: x[1], reverse=True)
    return {"by_paytype": by_paytype, "total": float(sum(totals.values(), Decimal(0)))}


async def get_range_daily(date_from: date, date_to: date) -> list[dict]:
    """Per-day per-paytype rows for the dashboard, with a 5-minute cache.

    Returns [] when not configured; raises on API errors (caller decides).
    """
    if not is_configured():
        return []
    key = (date_from.isoformat(), date_to.isoformat())
    now = time.monotonic()
    hit = _cache.get(key)
    if hit and now - hit[0] < _CACHE_TTL:
        return hit[1]

    client = IikoServerClient()
    rows = await client.sales_by_paytype(date_from, date_to)
    _cache[key] = (now, rows)
    # Trim stale cache entries
    for k in [k for k, (ts, _) in _cache.items() if now - ts > _CACHE_TTL * 4]:
        _cache.pop(k, None)
    return rows
