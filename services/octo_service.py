"""Octo (АО «Октобанк») internet-acquiring helpers — refunds.

Credentials come from env (OCTO_SHOP_ID / OCTO_SECRET in .env) — the same
shop the website uses for accepting payments.
"""

import aiohttp

from bot.config import settings

OCTO_API = "https://secure.octo.uz"


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
