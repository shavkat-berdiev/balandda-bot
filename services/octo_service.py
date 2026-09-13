"""Octo (АО «Октобанк») internet-acquiring helpers — refunds.

Credentials come from env (OCTO_SHOP_ID / OCTO_SECRET in .env) — the same
shop the website uses for accepting payments.
"""

from datetime import datetime

import aiohttp

from bot.config import settings

OCTO_API = "https://secure.octo.uz"


async def octo_prepare(
    *, shop_transaction_id: str, total_sum: float, description: str,
    return_url: str, notify_url: str, language: str = "ru", ttl: int = 1440,
    currency: str = "UZS",
) -> tuple[str | None, str | None, str]:
    """Create a payment and return (pay_url, payment_uuid, message).

    Mirrors what the website does in book.php so bot bookings and website
    bookings are the same Octo shop and the same money flow. NB: `user_data`
    is omitted on purpose - Octo rejects it with error 10.
    """
    if not settings.octo_shop_id or not settings.octo_secret:
        return None, None, "OCTO_SHOP_ID/OCTO_SECRET не настроены на сервере"
    body = {
        "octo_shop_id": settings.octo_shop_id,
        "octo_secret": settings.octo_secret,
        "shop_transaction_id": shop_transaction_id,
        "auto_capture": True,
        "init_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "test": False,
        "total_sum": round(float(total_sum), 2),
        "currency": currency if currency in ("UZS", "USD", "RUB") else "UZS",
        "description": description[:250],
        "return_url": return_url,
        "notify_url": notify_url,
        "language": language if language in ("ru", "uz", "en") else "ru",
        "ttl": ttl,
    }
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(
                f"{OCTO_API}/prepare_payment", json=body,
                timeout=aiohttp.ClientTimeout(total=20),
            ) as r:
                j = await r.json(content_type=None)
    except Exception as e:
        return None, None, f"Octo недоступен: {e}"
    if isinstance(j, dict) and int(j.get("error", 1)) == 0:
        d = j.get("data") or {}
        if d.get("octo_pay_url"):
            return str(d["octo_pay_url"]), d.get("octo_payment_UUID"), "ok"
    msg = (j or {}).get("errMessage") or (j or {}).get("errorMessage") or "неизвестная ошибка"
    return None, None, str(msg)


async def octo_status(shop_transaction_id: str) -> dict | None:
    """Re-fetch a payment by OUR transaction id.

    The webhook body is never trusted - the same rule the website follows:
    ask Octo what actually happened before touching any money.
    """
    if not settings.octo_shop_id or not settings.octo_secret:
        return None
    body = {
        "octo_shop_id": settings.octo_shop_id,
        "octo_secret": settings.octo_secret,
        "shop_transaction_id": shop_transaction_id,
    }
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(
                f"{OCTO_API}/prepare_payment", json=body,
                timeout=aiohttp.ClientTimeout(total=20),
            ) as r:
                j = await r.json(content_type=None)
    except Exception:
        return None
    if isinstance(j, dict) and int(j.get("error", 1)) == 0:
        return j.get("data") or {}
    return None


async def octo_refund(payment_uuid: str, amount: float, shop_refund_id: str) -> tuple[bool, str]:
    """Refund (full or partial) a succeeded Octo payment back to the guest's card.

    Returns (ok, message). Never raises — callers treat a failed refund as a
    result to report, not an exception.
    """
    if not settings.octo_shop_id or not settings.octo_secret:
        return False, "OCTO_SHOP_ID/OCTO_SECRET не настроены на сервере"
    body = {
        "octo_shop_id": settings.octo_shop_id,
        "octo_secret": settings.octo_secret,
        "octo_payment_UUID": payment_uuid,
        "shop_refund_id": shop_refund_id,
        "amount": round(float(amount), 2),
    }
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(
                f"{OCTO_API}/refund", json=body,
                timeout=aiohttp.ClientTimeout(total=15),
            ) as r:
                j = await r.json(content_type=None)
    except Exception as e:  # network / JSON
        return False, f"Octo недоступен: {e}"
    if isinstance(j, dict) and int(j.get("error", 1)) == 0:
        status = (j.get("data") or {}).get("status", "pending")
        return True, str(status)
    msg = (j or {}).get("errMessage") or (j or {}).get("errorMessage") or "неизвестная ошибка"
    return False, str(msg)
