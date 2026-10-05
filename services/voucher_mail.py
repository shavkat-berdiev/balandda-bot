"""Send the booking voucher e-mail for a reservation and record the outcome.

One path for every sender — the Octo payment webhook (automatic) and the
calendar's «Отправить ваучер» button — so each attempt, success or failure,
lands in the booking's change log (action="email"). Before 2026-10 failures
were swallowed silently, which is how most confirmations went missing unnoticed.
"""

from __future__ import annotations

import asyncio
import re

from db.models import ReservationEvent
from services.mailer import send_email
from services.voucher import (
    build_email, build_email_html, build_voucher_pdf, load_voucher_data, norm_lang,
)

EMAIL_RE = re.compile(r"^[^@\s,;]+@[^@\s,;]+\.[^@\s,;]{2,}$")


def clean_email(raw: str | None) -> str | None:
    """Trimmed, validated address or None. Raises ValueError on a malformed one."""
    if raw is None:
        return None
    e = raw.strip()
    if not e:
        return None
    if not EMAIL_RE.match(e) or len(e) > 160:
        raise ValueError("invalid e-mail")
    return e


async def guess_lang(session, res) -> str:
    """Guest language: the customer card's language, else +998 → ru, else en."""
    if getattr(res, "customer_id", None):
        from db.models import Customer
        c = await session.get(Customer, res.customer_id)
        if c is not None and c.language:
            return norm_lang(c.language)
    digits = "".join(ch for ch in (res.guest_phone or "") if ch.isdigit())
    if not digits or digits.startswith("998") or len(digits) == 9:
        return "ru"
    return "en"


async def send_booking_voucher(session, res, email: str, lang: str | None = None,
                               actor_name: str = "Система", actor_id: int | None = None,
                               paid_card: str | None = None) -> tuple[bool, str | None]:
    lg = norm_lang(lang) if lang else await guess_lang(session, res)
    err = None
    try:
        vd = await load_voucher_data(session, res, lg, paid_card=paid_card)
        subject, text = build_email(lg, vd)
        html = build_email_html(lg, vd)
        pdf = build_voucher_pdf(lg, vd)
        ok = await asyncio.to_thread(
            send_email, email, subject, text, f"balandda-voucher-{res.id}.pdf", pdf, html,
        )
        if not ok:
            err = "SMTP не настроен"
    except Exception as e:  # noqa: BLE001 — any failure is reported, never raised
        err = f"{type(e).__name__}: {e}"[:300]
    detail = (f"Ваучер ({lg.upper()}) отправлен на {email}" if err is None
              else f"Ваучер ({lg.upper()}) НЕ отправлен на {email}: {err}")
    session.add(ReservationEvent(reservation_id=res.id, actor_id=actor_id, actor_name=actor_name,
                                 action="email", detail=detail))
    await session.commit()
    return err is None, err
