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


async def notify_operators_booking(res, unit_name: str, source_label: str = "сайт") -> bool:
    """Announce a non-bot booking (website self-booking) to the operators' Брони topic
    via the CRM. Best-effort — never breaks the booking flow."""
    if not settings.bridge_secret:
        return False
    url = settings.crm_api_url.rstrip("/") + "/api/operator-booking"
    payload = {
        "booking_id": res.id,
        "unit_name": unit_name,
        "check_in": res.check_in.isoformat(),
        "check_out": res.check_out.isoformat(),
        "guest_name": res.guest_name,
        "guest_phone": res.guest_phone,
        "source_label": source_label,
    }
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(
                url, json=payload,
                headers={"X-Bridge-Secret": settings.bridge_secret},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as r:
                if r.status >= 400:
                    logger.warning("operator-booking CRM failed %s: %s", r.status, await r.text())
                    return False
                return True
    except Exception as e:  # noqa: BLE001 - best effort
        logger.warning("operator-booking CRM error: %s", e)
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
        total = float(res.total_amount)
        deposit = round(total * 0.2)
        lines.append(f"• Сумма: <b>{_fmt_amount(total)}</b> сум")
        lines.append(f"• Предоплата 20%: <b>{_fmt_amount(deposit)}</b> сум")
    lines += ["", prepay_text or settings.prepayment_instructions]
    return "\n".join(lines)


def booking_confirmed_text(res, property_name: str) -> str:
    return (
        "✅ <b>Бронь подтверждена!</b>\n\n"
        f"• Объект: <b>{property_name}</b>\n"
        f"• Даты: <b>{_dates(res)}</b>\n\n"
        "Спасибо, что выбрали Balandda Chimgan. Ждём вас! 🏔"
    )


def booking_payment_text(res, property_name: str, amount, paid, total) -> str:
    lines = ["💳 <b>Оплата получена</b>", "", f"Спасибо! Мы получили {_fmt_amount(amount)} сум."]
    if total:
        balance = max(0, float(total) - float(paid))
        tail = " ✓ Оплачено полностью" if balance <= 0 else f" · остаток {_fmt_amount(balance)} сум"
        lines.append(f"Оплачено: {_fmt_amount(paid)} из {_fmt_amount(total)} сум{tail}")
    lines += ["", f"Объект: <b>{property_name}</b> · {_dates(res)}"]
    return "\n".join(lines)


def booking_cancelled_text(res, property_name: str) -> str:
    return (
        "❌ <b>Ваша бронь отменена</b>\n\n"
        f"• Объект: <b>{property_name}</b>\n"
        f"• Даты: <b>{_dates(res)}</b>\n\n"
        "Если это ошибка — пожалуйста, свяжитесь с нами."
    )


def booking_changed_text(res, property_name: str) -> str:
    return (
        "✏️ <b>Ваша бронь изменена</b>\n\n"
        "Актуальные данные:\n"
        f"• Объект: <b>{property_name}</b>\n"
        f"• Даты: <b>{_dates(res)}</b>"
    )
