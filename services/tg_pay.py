"""Payment requests and vouchers sent to a guest in Telegram (2026-10).

Built for bookings an operator makes from a @balandda_chimgan chat (`/бронь`), but works
for any booking linked to a Telegram user: the CRM delivers into the chimgan chat or the
@balandda_bot chat, whichever reaches the guest (see CRM /api/notify).

Pay buttons are plain URL buttons pointing at /api/v1/bridge/pay/{id}/{kind}/{sig}. The
Octo payment is created only when the guest taps — so an option they don't choose never
leaves a dangling payment — and the signature means a link can't be forged for another
booking or amount kind.
"""

from __future__ import annotations

import hashlib
import hmac

from bot.config import settings
from services.voucher import CONTACT, _fmt_sum, fmt_date, norm_lang

PUBLIC_BASE = "https://calendar.balandda.uz"
KINDS = ("deposit", "full", "balance")


def sign(res_id: int, kind: str) -> str:
    msg = f"pay:{int(res_id)}:{kind}".encode()
    return hmac.new((settings.bridge_secret or "").encode(), msg, hashlib.sha256).hexdigest()[:20]


def verify(res_id: int, kind: str, sig: str) -> bool:
    return kind in KINDS and bool(settings.bridge_secret) and hmac.compare_digest(sign(res_id, kind), sig or "")


def pay_url(res_id: int, kind: str) -> str:
    return f"{PUBLIC_BASE}/api/v1/bridge/pay/{int(res_id)}/{kind}/{sign(res_id, kind)}"


T = {
    "ru": {
        "title": "🗓 <b>Бронь №{id}</b> — {unit}",
        "dates": "Заезд: {ci}, с {tin}\nВыезд: {co}, до {tout} · {n} ноч.",
        "total": "Стоимость: <b>{v} сум</b>",
        "paid": "Оплачено: {v} сум",
        "due": "К оплате: <b>{v} сум</b>",
        "ask_new": "Чтобы подтвердить бронь, внесите предоплату 20% или оплатите проживание полностью со скидкой 5%. "
                   "Принимаем Uzcard, Humo, Visa и Mastercard.",
        "ask_bal": "Остаток можно оплатить онлайн по кнопке ниже или при заселении.",
        "b_dep": "💳 Предоплата 20% — {v} сум",
        "b_full": "✅ Оплатить 100% со скидкой 5% — {v} сум",
        "b_bal": "💳 Оплатить остаток — {v} сум",
        "help": "Вопросы — ресепшн {phone}.",
        "b_bot": "🔔 Получать ваучер и уведомления в боте",
        "voucher": "📄 Ваучер по брони №{id} — покажите его при заселении (можно с экрана телефона).",
    },
    "uz": {
        "title": "🗓 <b>Bron №{id}</b> — {unit}",
        "dates": "Kelish: {ci}, soat {tin} dan\nKetish: {co}, soat {tout} gacha · {n} kecha",
        "total": "Narxi: <b>{v} so'm</b>",
        "paid": "To'langan: {v} so'm",
        "due": "To'lanishi kerak: <b>{v} so'm</b>",
        "ask_new": "Bronni tasdiqlash uchun 20% oldindan to'lov qiling yoki 5% chegirma bilan to'liq to'lang. "
                   "Uzcard, Humo, Visa va Mastercard qabul qilinadi.",
        "ask_bal": "Qolgan summani quyidagi tugma orqali yoki joylashishda to'lashingiz mumkin.",
        "b_dep": "💳 20% oldindan to'lov — {v} so'm",
        "b_full": "✅ 100% to'lov, 5% chegirma — {v} so'm",
        "b_bal": "💳 Qolganini to'lash — {v} so'm",
        "help": "Savollar bo'lsa — resepshn {phone}.",
        "b_bot": "🔔 Vaucher va xabarnomalarni botda olish",
        "voucher": "📄 Bron №{id} vaucheri — joylashishda ko'rsating (telefon ekranidan ham bo'ladi).",
    },
    "en": {
        "title": "🗓 <b>Booking #{id}</b> — {unit}",
        "dates": "Check-in: {ci}, from {tin}\nCheck-out: {co}, until {tout} · {n} night(s)",
        "total": "Stay total: <b>{v} UZS</b>",
        "paid": "Paid: {v} UZS",
        "due": "Balance due: <b>{v} UZS</b>",
        "ask_new": "To confirm your booking, pay a 20% deposit — or pay in full and get 5% off. "
                   "Uzcard, Humo, Visa and Mastercard are accepted.",
        "ask_bal": "You can pay the balance online below or at check-in.",
        "b_dep": "💳 20% deposit — {v} UZS",
        "b_full": "✅ Pay 100% with 5% off — {v} UZS",
        "b_bal": "💳 Pay the balance — {v} UZS",
        "help": "Questions — reception {phone}.",
        "b_bot": "🔔 Get the voucher and updates in our bot",
        "voucher": "📄 Voucher for booking #{id} — show it at check-in (a phone screen is fine).",
    },
}


def pay_message(lang: str, vd: dict, connect_url: str | None = None) -> tuple[str, list[list[dict]]]:
    """(HTML text, URL-button rows) for a payment request. `vd` = load_voucher_data().

    `connect_url` adds a «get it in the bot» button (t.me/balandda_bot?start=connect_…).
    Telegram lets the bot write in a @balandda_chimgan chat only within 24 h of the guest's
    last message (BUSINESS_PEER_USAGE_MISSING otherwise); a guest who pressed Start in
    @balandda_bot stays reachable for the voucher and status updates after that."""
    lg = norm_lang(lang)
    t = T[lg]
    total = float(vd.get("total_amount") or 0)
    paid = float(vd.get("paid_amount") or 0)
    bal = max(0.0, total - paid)
    lines = [
        t["title"].format(id=vd["booking_id"], unit=vd.get("unit") or ""),
        t["dates"].format(ci=fmt_date(lg, vd["check_in"]), co=fmt_date(lg, vd["check_out"]),
                          tin=vd.get("t_in"), tout=vd.get("t_out"), n=vd.get("nights") or 0),
        "",
    ]
    rows: list[list[dict]] = []
    if total > 0:
        lines.append(t["total"].format(v=_fmt_sum(total)))
    if paid > 0:
        lines.append(t["paid"].format(v=_fmt_sum(paid)))
        if bal > 0:
            lines.append(t["due"].format(v=_fmt_sum(bal)))
            lines += ["", t["ask_bal"]]
            rows.append([{"text": t["b_bal"].format(v=_fmt_sum(bal)), "url": pay_url(vd["booking_id"], "balance")}])
    elif total > 0:
        lines += ["", t["ask_new"]]
        rows.append([{"text": t["b_dep"].format(v=_fmt_sum(round(total * 0.2))),
                      "url": pay_url(vd["booking_id"], "deposit")}])
        rows.append([{"text": t["b_full"].format(v=_fmt_sum(round(total * 0.95))),
                      "url": pay_url(vd["booking_id"], "full")}])
    lines += ["", t["help"].format(phone=CONTACT["phone"])]
    if rows and connect_url:
        rows.append([{"text": t["b_bot"], "url": connect_url}])
    return "\n".join(lines), rows


def voucher_caption(lang: str, booking_id: int) -> str:
    return T[norm_lang(lang)]["voucher"].format(id=booking_id)
