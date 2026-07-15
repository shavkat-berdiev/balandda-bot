"""Billz POS API client — REST (api-admin.billz.ai).

Used to pull cash sales data for the XUSH business unit.
Auth: POST /v1/auth/login with secret_token → Bearer access_token.
"""

import logging
from datetime import date, datetime
from decimal import Decimal
from typing import Any

import httpx

from bot.config import settings

logger = logging.getLogger(__name__)

BASE_URL = "https://api-admin.billz.ai"
AUTH_ENDPOINT = "/v1/auth/login"


class BillzClient:
    """Thin async wrapper around the Billz REST API."""

    def __init__(self, secret_token: str | None = None):
        self.secret_token = secret_token or settings.billz_api_key
        self._access_token: str | None = None

    async def _authenticate(self) -> str:
        """Obtain a Bearer access_token."""
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                f"{BASE_URL}{AUTH_ENDPOINT}",
                json={"secret_token": self.secret_token},
            )
            resp.raise_for_status()
            data = resp.json()
            token = data.get("data", {}).get("access_token") or data.get("access_token")
            if not token:
                raise ValueError(f"Billz auth response missing access_token: {data}")
            self._access_token = token
            logger.info("Billz auth OK")
            return token

    async def _get_token(self) -> str:
        if not self._access_token:
            return await self._authenticate()
        return self._access_token

    async def _request(self, method: str, path: str, **kwargs) -> Any:
        """Make an authenticated request, retry once on 401."""
        token = await self._get_token()
        headers = {"Authorization": f"Bearer {token}"}
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await getattr(client, method)(
                f"{BASE_URL}{path}", headers=headers, **kwargs,
            )
            if resp.status_code == 401:
                # Token expired — re-auth and retry
                token = await self._authenticate()
                headers["Authorization"] = f"Bearer {token}"
                resp = await getattr(client, method)(
                    f"{BASE_URL}{path}", headers=headers, **kwargs,
                )
            resp.raise_for_status()
            return resp.json()

    # ── High-level helpers ──────────────────────────────────────────

    async def get_shops(self) -> list[dict]:
        """List all shops/offices."""
        data = await self._request("get", "/v1/shop")
        return data.get("data", data.get("shops", []))

    async def get_payment_types(self) -> list[dict]:
        """List available payment types."""
        data = await self._request("get", "/v1/company-payment-type")
        return data.get("data", [])

    async def get_orders(
        self,
        date_from: date,
        date_to: date,
        shop_id: int | None = None,
        page: int = 1,
        limit: int = 100,
    ) -> dict:
        """Get orders/cheques for a date range.

        Returns { orders: [...], total: int }.
        Each order has payment_details with payment type breakdown.
        """
        params: dict[str, Any] = {
            "date_from": date_from.isoformat(),
            "date_to": date_to.isoformat(),
            "page": page,
            "limit": limit,
        }
        if shop_id:
            params["shop_id"] = shop_id
        data = await self._request("get", "/v1/orders", params=params)
        return data.get("data", data)

    async def get_daily_cash_total(
        self,
        target_date: date | None = None,
        shop_id: int | None = None,
    ) -> dict:
        """Get total cash payments for a given day.

        Returns {
            cash_total: Decimal,
            card_total: Decimal,
            other_total: Decimal,
            order_count: int,
            details: [...],  # per-payment-type breakdown
        }
        """
        d = target_date or date.today()
        orders_data = await self.get_orders(d, d, shop_id=shop_id, limit=500)

        cash_total = Decimal(0)
        card_total = Decimal(0)
        other_total = Decimal(0)
        order_count = 0
        payment_breakdown: dict[str, Decimal] = {}

        orders = orders_data if isinstance(orders_data, list) else orders_data.get("orders", [])

        for order in orders:
            order_count += 1
            # Try to extract payment details from the order
            payments = order.get("payment_details") or order.get("payments") or []
            if isinstance(payments, dict):
                payments = [payments]

            for p in payments:
                ptype = p.get("payment_type", {}).get("name", "") or p.get("type", "")
                amount = Decimal(str(p.get("amount", 0)))
                ptype_lower = ptype.lower()

                payment_breakdown[ptype] = payment_breakdown.get(ptype, Decimal(0)) + amount

                if any(kw in ptype_lower for kw in ("наличн", "cash", "naqd")):
                    cash_total += amount
                elif any(kw in ptype_lower for kw in ("uzcard", "humo", "visa", "terminal", "карт")):
                    card_total += amount
                else:
                    other_total += amount

        return {
            "cash_total": cash_total,
            "card_total": card_total,
            "other_total": other_total,
            "order_count": order_count,
            "details": [
                {"type": k, "amount": float(v)} for k, v in payment_breakdown.items()
            ],
        }


# Module-level singleton
_client: BillzClient | None = None


def get_billz_client() -> BillzClient:
    global _client
    if _client is None:
        _client = BillzClient()
    return _client
