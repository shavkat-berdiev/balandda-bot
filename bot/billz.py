"""Billz POS API client — BILLZ 2.0 REST (api-admin.billz.ai).

Used to pull sales data for the XUSH business unit.
Auth: POST /v1/auth/login with secret_token → Bearer access_token.
Sales: GET /v3/order-search (documented in the BILLZ 2.0 Notion API docs).
Payment types: GET /v1/company-payment-type.
"""

import logging
from datetime import date
from decimal import Decimal
from typing import Any

import httpx

from bot.config import settings

logger = logging.getLogger(__name__)

BASE_URL = "https://api-admin.billz.ai"
AUTH_ENDPOINT = "/v1/auth/login"

CASH_KEYWORDS = ("наличн", "cash", "naqd")
CARD_KEYWORDS = ("uzcard", "humo", "visa", "terminal", "терминал", "карт")


class BillzClient:
    """Thin async wrapper around the BILLZ 2.0 REST API."""

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
        """Make an authenticated request, retry once on 401/403."""
        token = await self._get_token()
        headers = {"Authorization": f"Bearer {token}", "accept": "application/json"}
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await getattr(client, method)(
                f"{BASE_URL}{path}", headers=headers, **kwargs,
            )
            if resp.status_code in (401, 403):
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
        data = await self._request("get", "/v1/shop", params={"limit": 100})
        if isinstance(data, list):
            return data
        return data.get("shops") or data.get("data") or []

    async def get_payment_types(self) -> list[dict]:
        """List available payment types: [{id, name}, ...]."""
        data = await self._request(
            "get", "/v1/company-payment-type", params={"limit": 1000}
        )
        if isinstance(data, list):
            return data
        for key in ("payment_types", "company_payment_types", "data"):
            if isinstance(data.get(key), list):
                return data[key]
        return []

    async def search_orders(
        self,
        date_from: date,
        date_to: date,
        payment_type_id: str | None = None,
        shop_ids: str | None = None,
        limit: int = 500,
        max_pages: int = 10,
    ) -> list[dict]:
        """Fetch orders via /v3/order-search, flattened across dates and pages.

        Response shape: {count, orders_sorted_by_date_list: [{date, orders: [...]}]}
        """
        orders: list[dict] = []
        for page in range(1, max_pages + 1):
            params: dict[str, Any] = {
                "start_date": date_from.isoformat(),
                "end_date": date_to.isoformat(),
                "limit": limit,
                "page": page,
            }
            if payment_type_id:
                params["company_payment_type_ids"] = payment_type_id
            if shop_ids:
                params["shop_ids"] = shop_ids

            data = await self._request("get", "/v3/order-search", params=params)
            if isinstance(data, dict) and "data" in data and isinstance(data["data"], dict):
                data = data["data"]

            page_orders = []
            for day in (data.get("orders_sorted_by_date_list") or []):
                page_orders.extend(day.get("orders") or [])
            orders.extend(page_orders)

            total_count = data.get("count")
            if not page_orders or (total_count is not None and len(orders) >= total_count):
                break
        return orders

    @staticmethod
    def _order_amount(order: dict) -> Decimal:
        detail = order.get("order_detail") or {}
        return Decimal(str(detail.get("total_price") or 0))

    @staticmethod
    def _is_sale(order: dict) -> bool:
        if order.get("deleted"):
            return False
        return (order.get("order_type") or "SALE").upper() == "SALE"

    async def get_daily_cash_total(
        self,
        target_date: date | None = None,
        shop_id: str | None = None,
    ) -> dict:
        """Total sales for a given day, split by payment type.

        Returns {
            cash_total: Decimal,
            card_total: Decimal,
            other_total: Decimal,
            order_count: int,
            details: [{type, amount}, ...],  # per-payment-type breakdown
        }
        Note: an order paid with a split (e.g. cash + card) counts toward each
        of its payment types, so the per-type sum can slightly exceed the
        order total sum in that case.
        """
        d = target_date or date.today()

        # All sales of the day (authoritative total + count)
        all_orders = await self.search_orders(d, d, shop_ids=shop_id)
        sales = [o for o in all_orders if self._is_sale(o)]
        order_count = len(sales)

        cash_total = Decimal(0)
        card_total = Decimal(0)
        other_total = Decimal(0)
        payment_breakdown: dict[str, Decimal] = {}

        # Per-payment-type split via the company_payment_type_ids filter
        try:
            ptypes = await self.get_payment_types()
        except Exception as e:
            logger.warning(f"Billz payment types unavailable: {e}")
            ptypes = []

        classified_ids = set()
        for pt in ptypes:
            pt_id = pt.get("id")
            pt_name = pt.get("name") or pt.get("payment_type_name") or "?"
            if not pt_id:
                continue
            try:
                pt_orders = await self.search_orders(d, d, payment_type_id=pt_id, shop_ids=shop_id)
            except Exception as e:
                logger.warning(f"Billz order-search for payment type '{pt_name}' failed: {e}")
                continue
            amount = sum((self._order_amount(o) for o in pt_orders if self._is_sale(o)), Decimal(0))
            if amount == 0:
                continue
            classified_ids.add(pt_id)
            payment_breakdown[pt_name] = payment_breakdown.get(pt_name, Decimal(0)) + amount

            name_lower = pt_name.lower()
            if any(kw in name_lower for kw in CASH_KEYWORDS):
                cash_total += amount
            elif any(kw in name_lower for kw in CARD_KEYWORDS):
                card_total += amount
            else:
                other_total += amount

        # If the payment-type split yielded nothing, fall back to the grand total as "other"
        if not payment_breakdown and sales:
            grand = sum((self._order_amount(o) for o in sales), Decimal(0))
            other_total = grand
            payment_breakdown["Все продажи"] = grand

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
