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


async def crm_request(method: str, path: str, json: dict | None = None, timeout: float = 30) -> tuple[int, dict]:
    """Call the CRM bridge (X-Bridge-Secret). Returns (http_status, json_body); 0 on network error."""
    if not settings.bridge_secret:
        return 0, {"ok": False, "error": "bridge secret not set"}
    url = settings.crm_api_url.rstrip("/") + path
    try:
        async with aiohttp.ClientSession() as s:
            async with s.request(
                method, url, json=json,
                headers={"X-Bridge-Secret": settings.bridge_secret},
                timeout=aiohttp.ClientTimeout(total=timeout),
            ) as r:
                try:
                    data = await r.json(content_type=None)
                except Exception:  # noqa: BLE001
                    data = {"ok": False, "error": (await r.text())[:300]}
                return r.status, (data if isinstance(data, dict) else {"ok": False, "data": data})
    except Exception as e:  # noqa: BLE001 - best effort
        logger.warning("CRM %s %s error: %s", method, path, e)
        return 0, {"ok": False, "error": str(e)}


async def crm_notify(telegram_user_id: int | None, text: str | None = None, *, via: str | None = None,
                     buttons: list | None = None, document: tuple[str, bytes] | None = None) -> dict:
    """Deliver to a guest's Telegram through the CRM. Since 2026-10 the CRM reaches them in
    their @balandda_chimgan chat (business connection) or the @balandda_bot chat, whichever
    works — `via` only picks which to try first. Returns {ok, via, error}."""
    if not telegram_user_id:
        return {"ok": False, "error": "бронь не привязана к Telegram"}
    body: dict = {"telegram_user_id": int(telegram_user_id)}
    if text:
        body["text"] = text
    if via:
        body["via"] = via
    if buttons:
        body["buttons"] = buttons
    if document:
        import base64
        body["document"] = {"filename": document[0], "base64": base64.b64encode(document[1]).decode()}
    status, data = await crm_request("POST", "/api/notify", body, timeout=60 if document else 15)
    if status == 200 and data.get("ok"):
        return {"ok": True, "via": data.get("via")}
    logger.warning("notify CRM failed %s: %s", status, data)
    return {"ok": False, "error": data.get("error") or f"HTTP {status}"}


async def send_customer_message(telegram_user_id: int | None, text: str) -> bool:
    """Deliver `text` to the customer's Telegram (chimgan chat or @balandda_bot)."""
    if not telegram_user_id or not settings.bridge_secret:
        return False
    return (await crm_notify(telegram_user_id, text))["ok"]


async def notify_operators_booking(
    res, unit_name: str, source_label: str = "сайт",
    kind: str = "site", ref: str | None = None,
    link: str | None = None, amount_text: str | None = None,
    nights: int | None = None, status: str | None = None,
) -> bool:
    """Announce a booking to the operators via the CRM, which owns the group.

    Since 2026-09-29 the CRM renders ONE stateful card per booking — Принял / Связался /
    Предоплату получил / Бронь подтверждена / Бронь отменена — and routes it by `kind`
    ("site"/"bot"/"instagram" → «Брони», "ota" → «Брони платформ»). Channel bookings used
    to be posted twice: once here and once directly by services/beds24.py into «Брони
    платформ», so every Booking.com reservation appeared in two topics.

    `ref` is the idempotency key: a retry edits the existing card instead of adding one.
    Best-effort — never breaks the booking flow.
    """
    if not settings.bridge_secret:
        return False
    url = settings.crm_api_url.rstrip("/") + "/api/operator-booking"
    payload = {
        "kind": kind,
        "ref": str(ref if ref is not None else res.id),
        "booking_id": res.id,
        "unit_name": unit_name,
        "check_in": res.check_in.isoformat(),
        "check_out": res.check_out.isoformat(),
        "guest_name": res.guest_name,
        "guest_phone": res.guest_phone,
        "source_label": source_label,
        "channel_label": source_label,
    }
    if link:
        payload["link"] = link
    if amount_text:
        payload["amount_text"] = amount_text
    if nights is not None:
        payload["nights"] = nights
    if status:
        payload["status"] = status
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
