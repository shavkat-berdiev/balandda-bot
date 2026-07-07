"""Customer-facing Telegram messaging.

@balandda_bot lives in the CRM project, so we deliver messages by POSTing to the
CRM bridge (`/api/notify`), which sends via @balandda_bot. Also builds the message
texts (booking received / confirmed). All sends are best-effort — a delivery failure
must never break the booking flow.
"""

import logging
import time

import aiohttp

from bot.config import settings

logger = logging.getLogger(__name__)

# Cache the live-editable prepayment text briefly so we don't hit the website on every send.
_prepay_cache: dict = {"text": None, "ts": 0.0}


async def get_prepayment_instructions() -> str:
    """Fetch the current prepayment text from the website admin, cached ~60s;
    falls back to the config default if the site is unreachable or empty."""
    now = time.time()
    if _prepay_cache["text"] is not None and now - _prepay_cache["ts"] < 60:
        return _prepay_cache["text"]
    text = settings.prepayment_instructions
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(settings.prepayment_url, timeout=aiohttp.ClientTimeout(total=6)) as r:
                if r.status < 400:
                    fetched = (await r.text()).strip()
                    if fetched:
                        text = fetched
    except Exception as e:  # noqa: BLE001 - best effort, keep default
        logger.warning("prepayment text fetch failed: %s", e)
    _prepay_cache["text"] = text
    _prepay_cache["ts"] = now
    return text


async def send_customer_message(telegram_user_id: int | None, text: str) -> bool:
    """Ask the CRM to deliver `text` to the customer via @balandda_bot."""
    if not telegram_user_id or not settings.bridge_secret:
        return False
    url = settings.crm_api_url.rstrip("/") + "/api/notify"
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(
                url,
                json={"telegram_user_id": telegram_user_id, "text": text},
                headers={"X-Bridge-Secret": settings.bridge_secret},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as r:
                if r.status >= 400:
                    logger.warning("notify CRM failed %s: %s", r.status, await r.text())
                    return False
                return True
    except Exception as e:  # noqa: BLE001 - best effort
        logger.warning("notify CRM error: %s", e)
        return False


def _fmt_amount(n) -> str:
    try:
        return f"{int(round(float(n))):,}".replace(",", " ")
    except (TypeError, ValueError):
        return str(n)


def _dates(res) -> str:
    return f"{res.check_in.strftime('%d.%m.%Y')} — {res.check_out.strftime('%d.%m.%Y')}"


def booking_received_text(res, property_name: str, prepay_text: str | None = None) -> str:
    lines = [
        "🏔 <b>Balandda Chimgan</b>",
        "",
        "Ваша бронь принята и ожидает подтверждения предоплатой:",
        f"• Объект: <b>{property_name}</b>",
        f"• Даты: <b>{_dates(res)}</b>",
    ]
    if res.total_amount:
        lines.append(f"• Сумма: <b>{_fmt_amount(res.total_amount)}</b> сум")
    lines += ["", prepay_text or settings.prepayment_instructions]
    return "\n".join(lines)


def booking_confirmed_text(res, property_name: str) -> str:
    return (
        "✅ <b>Бронь подтверждена!</b>\n\n"
        f"• Объект: <b>{property_name}</b>\n"
        f"• Даты: <b>{_dates(res)}</b>\n\n"
        "Спасибо, что выбрали Balandda Chimgan. Ждём вас! 🏔"
    )
