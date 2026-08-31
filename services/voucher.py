"""Booking voucher PDF + confirmation e-mail texts (RU / UZ / EN).

Uses fpdf2 with the system DejaVu fonts (fonts-dejavu-core in the Docker
image) so Cyrillic renders correctly. Check-in/out times: 14:00/12:00 by
default, 15:00/13:00 for White Chalet and SPA suites (split cleaning slots).
"""

from __future__ import annotations

from fpdf import FPDF

FONT_DIR = "/usr/share/fonts/truetype/dejavu"

ADDRESS = {
    "ru": "Ташкентская область, Бостанлыкский район, Чимган, ул. Тошлокбет 2, дом 159",
    "uz": "Toshkent viloyati, Bo'stonliq tumani, Chimgan, Toshloqbet ko'chasi 2, 159-uy",
    "en": "Tashkent region, Bostanlyk district, Chimgan, Toshlokbet st. 2, 159",
}

L = {
    "ru": {
        "voucher": "ВАУЧЕР · ПОДТВЕРЖДЕНИЕ БРОНИРОВАНИЯ",
        "booking": "Бронирование №",
        "guest": "Гость",
        "unit": "Размещение",
        "checkin": "Заезд",
        "checkout": "Выезд",
        "from_t": "с",
        "till_t": "до",
        "guests": "Гостей",
        "nights": "Ночей",
        "paid": "ОПЛАЧЕНО",
        "card": "карта",
        "total": "Стоимость проживания",
        "addr": "Адрес",
        "contacts": "Контакты",
        "note": "Покажите этот ваучер при заселении (можно с экрана телефона). Документ сформирован автоматически и действителен без печати.",
        "free": "Гостям бесплатно: подогреваемый инфинити-бассейн. К вашим услугам SPA и ресторан.",
    },
    "uz": {
        "voucher": "VAUCHER · BRON TASDIQNOMASI",
        "booking": "Bron №",
        "guest": "Mehmon",
        "unit": "Joylashuv",
        "checkin": "Kelish",
        "checkout": "Ketish",
        "from_t": "soat",
        "till_t": "gacha",
        "guests": "Mehmonlar",
        "nights": "Kechalar",
        "paid": "TO'LANGAN",
        "card": "karta",
        "total": "Yashash narxi",
        "addr": "Manzil",
        "contacts": "Aloqa",
        "note": "Joylashishda ushbu vaucherni ko'rsating (telefon ekranidan ham bo'ladi). Hujjat avtomatik shakllantirilgan va muhrsiz haqiqiy.",
        "free": "Mehmonlarga bepul: isitiladigan infinity-basseyn. SPA va restoran xizmatingizda.",
    },
    "en": {
        "voucher": "VOUCHER · BOOKING CONFIRMATION",
        "booking": "Booking #",
        "guest": "Guest",
        "unit": "Accommodation",
        "checkin": "Check-in",
        "checkout": "Check-out",
        "from_t": "from",
        "till_t": "until",
        "guests": "Guests",
        "nights": "Nights",
        "paid": "PAID",
        "card": "card",
        "total": "Stay total",
        "addr": "Address",
        "contacts": "Contacts",
        "note": "Show this voucher at check-in (phone screen is fine). Generated automatically, valid without a stamp.",
        "free": "Free for guests: heated infinity pool. SPA and restaurant at your service.",
    },
}

INK = (18, 39, 51)
ACCENT = (0, 167, 225)
GREY = (91, 107, 115)
PAPER = (238, 245, 248)


def norm_lang(lang: str | None) -> str:
    lang = (lang or "ru").lower()
    if lang == "zh":
        return "en"
    return lang if lang in ("ru", "uz", "en") else "ru"


def checkin_times(property_type: str | None) -> tuple[str, str]:
    if property_type in ("WHITE_CHALET", "SPA_SUITE"):
        return "15:00", "13:00"
    return "14:00", "12:00"


def _fmt_sum(v) -> str:
    try:
        return f"{int(round(float(v))):,}".replace(",", " ")
    except (TypeError, ValueError):
        return str(v or "—")


def build_voucher_pdf(lang: str, d: dict) -> bytes:
    """d: booking_id, guest_name, unit, check_in, check_out (ISO dates),
    guests, nights, paid_amount, paid_card, total_amount, t_in, t_out."""
    t = L[norm_lang(lang)]
    pdf = FPDF(orientation="P", format="A5")
    pdf.set_auto_page_break(auto=True, margin=10)
    pdf.add_font("DejaVu", "", f"{FONT_DIR}/DejaVuSans.ttf")
    pdf.add_font("DejaVu", "B", f"{FONT_DIR}/DejaVuSans-Bold.ttf")
    pdf.add_page()

    # Header band
    pdf.set_fill_color(*INK)
    pdf.rect(0, 0, 148, 26, style="F")
    pdf.set_xy(10, 7)
    pdf.set_font("DejaVu", "B", 16)
    pdf.set_text_color(255, 255, 255)
    pdf.cell(0, 7, "BALANDDA CHIMGAN")
    pdf.set_xy(10, 15)
    pdf.set_font("DejaVu", "", 8)
    pdf.set_text_color(180, 210, 225)
    pdf.cell(0, 5, "balandda.uz · Chimgan mountains")

    pdf.set_xy(10, 32)
    pdf.set_font("DejaVu", "B", 11)
    pdf.set_text_color(*ACCENT)
    pdf.cell(0, 6, t["voucher"])
    pdf.set_xy(10, 39)
    pdf.set_font("DejaVu", "B", 14)
    pdf.set_text_color(*INK)
    pdf.cell(0, 7, f"{t['booking']}{d['booking_id']}")

    def row(y, label, value, bold=False):
        pdf.set_xy(10, y)
        pdf.set_font("DejaVu", "", 8)
        pdf.set_text_color(*GREY)
        pdf.cell(40, 6, label)
        pdf.set_xy(50, y)
        pdf.set_font("DejaVu", "B" if bold else "", 10)
        pdf.set_text_color(*INK)
        pdf.multi_cell(88, 6, str(value))

    y = 50
    row(y, t["guest"], d.get("guest_name") or "—", bold=True); y += 7
    row(y, t["unit"], d.get("unit") or "—", bold=True); y += 7
    row(y, t["checkin"], f"{d['check_in']} · {t['from_t']} {d['t_in']}"); y += 7
    row(y, t["checkout"], f"{d['check_out']} · {t['till_t']} {d['t_out']}"); y += 7
    row(y, t["guests"], f"{d.get('guests') or '—'}   ·   {t['nights']}: {d.get('nights') or '—'}"); y += 7
    if d.get("total_amount"):
        row(y, t["total"], f"{_fmt_sum(d['total_amount'])} UZS"); y += 7

    # PAID badge
    y += 3
    pdf.set_fill_color(226, 245, 233)
    pdf.rect(10, y, 128, 12, style="F")
    pdf.set_xy(14, y + 3)
    pdf.set_font("DejaVu", "B", 11)
    pdf.set_text_color(27, 122, 62)
    paid_line = f"{t['paid']}: {_fmt_sum(d.get('paid_amount'))} UZS"
    if d.get("paid_card"):
        paid_line += f"  ·  {t['card']} {d['paid_card']}"
    pdf.cell(0, 6, paid_line)
    y += 17

    pdf.set_fill_color(*PAPER)
    pdf.rect(10, y, 128, 26, style="F")
    pdf.set_xy(14, y + 3)
    pdf.set_font("DejaVu", "B", 8.5)
    pdf.set_text_color(*INK)
    pdf.cell(0, 5, t["addr"])
    pdf.set_xy(14, y + 8)
    pdf.set_font("DejaVu", "", 8.5)
    pdf.set_text_color(*GREY)
    pdf.multi_cell(120, 4.5, ADDRESS[norm_lang(lang)])
    pdf.set_xy(14, y + 18)
    pdf.set_font("DejaVu", "", 8.5)
    pdf.cell(0, 5, f"{t['contacts']}: +998 90 007 70 77 · t.me/balandda_chimgan · info@balandda.uz")
    y += 30

    pdf.set_xy(10, y)
    pdf.set_font("DejaVu", "", 7.5)
    pdf.set_text_color(*GREY)
    pdf.multi_cell(128, 4, t["free"] + "\n" + t["note"])

    return bytes(pdf.output())


SUBJ = {
    "ru": "Balandda Chimgan — бронирование №{id} подтверждено ✔",
    "uz": "Balandda Chimgan — №{id} bron tasdiqlandi ✔",
    "en": "Balandda Chimgan — booking #{id} confirmed ✔",
}

BODY = {
    "ru": (
        "Здравствуйте, {name}!\n\n"
        "Ваше бронирование в Balandda Chimgan подтверждено и оплачено. "
        "Ваучер — во вложении, покажите его при заселении (достаточно с экрана телефона).\n\n"
        "{unit}\n"
        "Заезд: {ci}, с {tin} · Выезд: {co}, до {tout}\n"
        "Оплачено: {paid} сум{card}\n\n"
        "Как добраться: {addr} — 2 км от канатной дороги Чимгана, ~1,5 часа от Ташкента.\n"
        "Гостям бесплатно: подогреваемый инфинити-бассейн. Также к вашим услугам SPA и ресторан.\n\n"
        "Вопросы или изменение брони: Telegram t.me/balandda_chimgan, телефон +998 90 007 70 77 (9:00–21:00), info@balandda.uz.\n"
        "Условия отмены и возврата: https://www.balandda.uz/offer.html (раздел 7).\n\n"
        "Ждём вас в горах!\n— Команда Balandda · balandda.uz"
    ),
    "uz": (
        "Assalomu alaykum, {name}!\n\n"
        "Balandda Chimgan'dagi broningiz tasdiqlandi va to'landi. "
        "Vaucher xatga ilova qilingan — joylashishda ko'rsating (telefon ekranidan ham bo'ladi).\n\n"
        "{unit}\n"
        "Kelish: {ci}, soat {tin} dan · Ketish: {co}, {tout} gacha\n"
        "To'langan: {paid} so'm{card}\n\n"
        "Manzil: {addr} — Chimgan kanat yo'lidan 2 km, Toshkentdan ~1,5 soat.\n"
        "Mehmonlarga bepul: isitiladigan infinity-basseyn. SPA va restoran xizmatingizda.\n\n"
        "Savollar yoki bronni o'zgartirish: Telegram t.me/balandda_chimgan, tel. +998 90 007 70 77 (9:00–21:00), info@balandda.uz.\n"
        "Bekor qilish va qaytarish shartlari: https://www.balandda.uz/offer.html (7-bo'lim).\n\n"
        "Tog'larda kutamiz!\n— Balandda jamoasi · balandda.uz"
    ),
    "en": (
        "Hello {name},\n\n"
        "Your booking at Balandda Chimgan is confirmed and paid. "
        "The voucher is attached — show it at check-in (a phone screen is fine).\n\n"
        "{unit}\n"
        "Check-in: {ci}, from {tin} · Check-out: {co}, until {tout}\n"
        "Paid: {paid} UZS{card}\n\n"
        "Getting there: {addr} — 2 km from the Chimgan cable car, ~1.5h from Tashkent.\n"
        "Free for guests: heated infinity pool. SPA and restaurant at your service.\n\n"
        "Questions or changes: Telegram t.me/balandda_chimgan, phone +998 90 007 70 77 (9:00–21:00), info@balandda.uz.\n"
        "Cancellation & refund terms: https://www.balandda.uz/offer.html (section 7).\n\n"
        "See you in the mountains!\n— Balandda team · balandda.uz"
    ),
}


def build_email(lang: str, d: dict) -> tuple[str, str]:
    """Returns (subject, plain-text body)."""
    lg = norm_lang(lang)
    subject = SUBJ[lg].format(id=d["booking_id"])
    card = f" · {L[lg]['card']} {d['paid_card']}" if d.get("paid_card") else ""
    body = BODY[lg].format(
        name=d.get("guest_name") or "",
        unit=d.get("unit") or "",
        ci=d["check_in"], co=d["check_out"],
        tin=d["t_in"], tout=d["t_out"],
        paid=_fmt_sum(d.get("paid_amount")),
        card=card,
        addr=ADDRESS[lg],
    )
    return subject, body
