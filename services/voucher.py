"""Booking voucher PDF + confirmation e-mail (RU / UZ / EN).

v2 (2026-10): two-page A4 voucher in the balandda.uz brand — hero photo of the
booked unit type, check-in/out cards, payment summary, directions with QR codes
(page 1) and a "Your stay" guide (page 2, accommodation only). The e-mail goes
out as HTML with a plain-text alternative.

Everything renders from local assets in services/voucher_assets (Montserrat,
photos, logo, lucide icons, pre-generated QR codes), so no network is needed.
Contacts and links live in CONTACT below — change them in one place.

Public API (used by api/routers/bridge.py and api/routers/reservations.py):
  norm_lang, checkin_times, build_voucher_pdf, build_email, build_email_html,
  build_cancel_email, load_voucher_data
"""

from __future__ import annotations

import io
import os
from datetime import date
from functools import lru_cache

from fpdf import FPDF

ASSETS = os.path.join(os.path.dirname(__file__), "voucher_assets")

CONTACT = {
    # Reception (on site, longer hours) — guests talk to reception once booked.
    "phone": "+998 99 018 70 77",
    "phone_tel": "+998990187077",
    "hours": "",
    "telegram": "t.me/balandda_admin",
    "telegram_url": "https://t.me/balandda_admin",
    "email": "info@balandda.uz",
    "site": "balandda.uz",
    "map_url": "https://g.page/r/CYq21GpVptwtEAo/",
    "menu": "menu.balandda.uz",
    "menu_url": "https://menu.balandda.uz/",
    "offer_url": "https://www.balandda.uz/offer.html",
}

# Brand (assets/css/site.css)
NAVY = (35, 51, 63)
NAVY_2 = (18, 39, 51)
BLUE = (0, 167, 225)
BLUE_XL = (212, 239, 252)
LIME = (202, 219, 68)
PAPER = (244, 247, 248)
INK = (23, 29, 41)
GREY = (110, 124, 132)
LINE = (222, 229, 233)
GREEN = (36, 133, 74)
AMBER = (196, 120, 0)
WHITE = (255, 255, 255)

# Hero photo per unit type: (file, vertical focus 0..1)
PHOTO = {
    "CHALET_WITH_SAUNA": ("chalet_03.jpg", 0.42),
    "CHALET_WITHOUT_SAUNA": ("chalet_03.jpg", 0.42),
    "WHITE_CHALET": ("chalet_01.jpg", 0.55),
    "APARTMENT": ("apart_1.jpg", 0.35),
    "PENTHOUSE": ("pent_1.jpg", 0.45),
    "VILLA": ("villa_1.jpg", 0.40),
    "SPA_SUITE": ("spa_01.jpg", 0.55),
}
PHOTO_DEFAULT = ("villa_1.jpg", 0.40)

ADDRESS = {
    "ru": "Ташкентская область, Бостанлыкский район, Чимган, ул. Тошлокбет 2, дом 159",
    "uz": "Toshkent viloyati, Bo'stonliq tumani, Chimgan, Toshloqbet ko'chasi 2, 159-uy",
    "en": "Tashkent region, Bostanlyk district, Chimgan, Toshlokbet st. 2, 159",
}

MONTHS = {
    "ru": ["января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа",
           "сентября", "октября", "ноября", "декабря"],
    "uz": ["yanvar", "fevral", "mart", "aprel", "may", "iyun", "iyul", "avgust",
           "sentabr", "oktabr", "noyabr", "dekabr"],
    "en": ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"],
}
WEEKDAYS = {
    "ru": ["пн", "вт", "ср", "чт", "пт", "сб", "вс"],
    "uz": ["dushanba", "seshanba", "chorshanba", "payshanba", "juma", "shanba", "yakshanba"],
    "en": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
}

T = {
    "en": {
        "confirmed": "BOOKING CONFIRMED",
        "pending": "AWAITING PREPAYMENT",
        "booking": "Booking #{id}",
        "nights_n": lambda n: f"{n} night" + ("" if n == 1 else "s"),
        "dear": "Dear {name},",
        "intro": "Thank you for choosing Balandda Chimgan — your booking is confirmed. "
                 "We look forward to welcoming you in the mountains!",
        "intro_pending": "Thank you for choosing Balandda Chimgan. Your dates are reserved; the booking "
                         "is confirmed as soon as the prepayment is received.",
        "checkin": "CHECK-IN", "checkout": "CHECK-OUT", "from": "from {t}", "until": "until {t}",
        "guest": "GUEST", "unit": "ACCOMMODATION", "guests": "GUESTS",
        "total": "Stay total", "paid": "Paid", "balance": "Balance due", "paid_full": "Paid in full",
        "not_paid": "Not paid yet", "uzs": "UZS",
        "getting": "Getting here",
        "getting_txt": "We are next to the Chimgan cable car, about 1.5 hours from Tashkent — the best road "
                       "is via Beldersay. Simply type “Balandda Chimgan” in Waze, Yandex Maps or Google Maps.",
        "scan_map": "Scan for directions",
        "before": "Before you arrive",
        "before_txt": "Please call or message our reception before you set off and let us know your approximate arrival time.",
        "scan_tg": "Message reception",
        "show": "Show this voucher at check-in — a phone screen is fine.",
        "valid": "Generated automatically · valid without a stamp",
        "stay_title": "Your stay at Balandda",
        "stay_sub": "Everything you need to know for a relaxed stay in the mountains.",
        "guide": [
            ("log-in", "Arrival & check-in",
             "Check-in is from 14:00 (15:00 for SPA suites and White Chalets). Feel free to arrive earlier: "
             "enjoy the pool, the views and lunch at our restaurant or terrace while we prepare your house."),
            ("log-out", "Check-out",
             "Check-out is until 12:00 (13:00 for SPA suites and White Chalets). After checking out you are "
             "welcome to stay by the pool and leave late in the evening."),
            ("coffee", "Breakfast",
             "Served in the restaurant from 8:30 to 10:30. Besides the buffet you can order shakshuka, "
             "an omelette, sausages and more — all included in your breakfast."),
            ("utensils", "Restaurant & terrace",
             "Lunch and dinner in the restaurant or on the terrace with mountain views. "
             "See the menu at menu.balandda.uz."),
            ("waves-ladder", "Pool & SPA",
             "The shared pool is heated during the summer season and is free for guests. SPA treatments are available on request."),
            ("wifi", "Wi-Fi & TV",
             "High-speed Wi-Fi covers the whole resort. Every TV has Netflix and ITV with prepaid "
             "subscriptions, plus YouTube."),
            ("bed-double", "In your house",
             "Comfortable bathrobes, spare bed linen for the sofas and toiletries are waiting for you."),
            ("flame", "Kitchen & BBQ",
             "The kitchen is fully equipped with cookware. Firewood and everything for a barbecue "
             "or kazan are in the yard."),
        ],
        "links": "Useful links", "l_map": "Directions", "l_menu": "Restaurant menu", "l_tg": "Telegram",
        "cancel": "Cancellation and refunds follow section 7 of our public offer: balandda.uz/offer.html",
        "see_you": "See you in the mountains!",
    },
    "ru": {
        "confirmed": "БРОНЬ ПОДТВЕРЖДЕНА",
        "pending": "ОЖИДАЕТ ПРЕДОПЛАТУ",
        "booking": "Бронь №{id}",
        "nights_n": lambda n: f"{n} " + ("ночь" if n % 10 == 1 and n % 100 != 11 else
                                         "ночи" if n % 10 in (2, 3, 4) and n % 100 not in (12, 13, 14) else "ночей"),
        "dear": "Уважаемый гость, {name}!",
        "intro": "Спасибо, что выбрали Balandda Chimgan — ваша бронь подтверждена. "
                 "Мы будем рады приветствовать вас в горах!",
        "intro_pending": "Спасибо, что выбрали Balandda Chimgan. Даты за вами закреплены; бронь будет "
                         "подтверждена сразу после получения предоплаты.",
        "checkin": "ЗАЕЗД", "checkout": "ВЫЕЗД", "from": "с {t}", "until": "до {t}",
        "guest": "ГОСТЬ", "unit": "РАЗМЕЩЕНИЕ", "guests": "ГОСТЕЙ",
        "total": "Стоимость", "paid": "Оплачено", "balance": "К оплате", "paid_full": "Оплачено полностью",
        "not_paid": "Ещё не оплачено", "uzs": "сум",
        "getting": "Как добраться",
        "getting_txt": "Мы находимся недалеко от канатной дороги Чимган, ~1,5 часа от Ташкента — ехать к нам "
                       "ближе по дороге через Белдерсай. Просто напишите «Balandda Chimgan» в Waze, "
                       "Яндекс Картах или Google Maps.",
        "scan_map": "Маршрут — сканируйте",
        "before": "Перед приездом",
        "before_txt": "Пожалуйста, позвоните или напишите на ресепшн перед выездом и сообщите примерное время прибытия.",
        "scan_tg": "Написать на ресепшн",
        "show": "Покажите этот ваучер при заселении — можно с экрана телефона.",
        "valid": "Сформирован автоматически · действителен без печати",
        "stay_title": "Ваш отдых в Balandda",
        "stay_sub": "Всё, что нужно знать для спокойного отдыха в горах.",
        "guide": [
            ("log-in", "Заезд",
             "Заезд в дома с 14:00 (в SPA-сьюты и Белые шале — с 15:00). Можно приехать раньше или с утра: "
             "насладитесь бассейном, видами и кухней нашего ресторана или террасы, пока мы готовим ваш дом."),
            ("log-out", "Выезд",
             "Выезд до 12:00 (из SPA-сьютов и Белых шале — до 13:00). После выезда можно остаться у бассейна "
             "и уехать поздно вечером."),
            ("coffee", "Завтрак",
             "Подаётся в ресторане с 8:30 до 10:30. Кроме шведского стола можно заказать шакшуку, омлет, "
             "сосиски и другие блюда — они включены в завтрак."),
            ("utensils", "Ресторан и терраса",
             "Обеды и ужины в ресторане или на террасе с видом на горы. Меню — на menu.balandda.uz."),
            ("waves-ladder", "Бассейн и SPA",
             "Общий бассейн с подогревом в летний сезон — бесплатно для гостей. SPA-процедуры — по предварительной записи."),
            ("wifi", "Wi-Fi и ТВ",
             "Высокоскоростной Wi-Fi работает на всей территории. На каждом телевизоре — Netflix и ITV "
             "с оплаченной подпиской, а также YouTube."),
            ("bed-double", "В вашем доме",
             "Удобные халаты, запасное постельное бельё для диванов и туалетные принадлежности."),
            ("flame", "Кухня и мангал",
             "Кухня полностью оснащена посудой. Во дворе — дрова и всё необходимое для мангала или казана."),
        ],
        "links": "Полезные ссылки", "l_map": "Маршрут", "l_menu": "Меню ресторана", "l_tg": "Telegram",
        "cancel": "Отмена брони и возврат — по разделу 7 публичной оферты: balandda.uz/offer.html",
        "see_you": "До встречи в горах!",
    },
    "uz": {
        "confirmed": "BRON TASDIQLANDI",
        "pending": "OLDINDAN TO'LOV KUTILMOQDA",
        "booking": "Bron №{id}",
        "nights_n": lambda n: f"{n} kecha",
        "dear": "Hurmatli {name}!",
        "intro": "Balandda Chimgan'ni tanlaganingiz uchun rahmat — broningiz tasdiqlandi. "
                 "Sizni tog'larda kutib olishdan xursand bo'lamiz!",
        "intro_pending": "Balandda Chimgan'ni tanlaganingiz uchun rahmat. Sanalar siz uchun band qilindi; "
                         "oldindan to'lov kelib tushishi bilan bron tasdiqlanadi.",
        "checkin": "KELISH", "checkout": "KETISH", "from": "soat {t} dan", "until": "soat {t} gacha",
        "guest": "MEHMON", "unit": "JOYLASHUV", "guests": "MEHMONLAR",
        "total": "Narxi", "paid": "To'langan", "balance": "To'lanishi kerak", "paid_full": "To'liq to'langan",
        "not_paid": "Hali to'lanmagan", "uzs": "so'm",
        "getting": "Qanday borish mumkin",
        "getting_txt": "Biz Chimgan kanat yo'li yaqinidamiz, Toshkentdan ~1,5 soat — eng qulay yo'l Beldersoy "
                       "orqali. Waze, Yandex yoki Google xaritalarida “Balandda Chimgan” deb yozing.",
        "scan_map": "Yo'nalish — skanerlang",
        "before": "Kelishdan oldin",
        "before_txt": "Yo'lga chiqishdan oldin resepshnga qo'ng'iroq qiling yoki yozing va taxminiy kelish vaqtingizni ayting.",
        "scan_tg": "Resepshnga yozing",
        "show": "Joylashishda ushbu vaucherni ko'rsating — telefon ekranidan ham bo'ladi.",
        "valid": "Avtomatik shakllantirilgan · muhrsiz haqiqiy",
        "stay_title": "Balandda'dagi dam olishingiz",
        "stay_sub": "Tog'larda xotirjam dam olish uchun bilishingiz kerak bo'lgan hamma narsa.",
        "guide": [
            ("log-in", "Kelish",
             "Uylarga joylashish soat 14:00 dan (SPA-syuitlar va Oq shalelarga — 15:00 dan). Ertaroq yoki "
             "ertalab kelishingiz mumkin: uyingiz tayyorlanayotganda basseyn, manzaralar va restoran yoki "
             "terassamiz taomlaridan bahramand bo'ling."),
            ("log-out", "Ketish",
             "Uydan chiqish soat 12:00 gacha (SPA-syuitlar va Oq shalelardan — 13:00 gacha). Chiqqaningizdan "
             "so'ng basseynda qolib, kechqurun ketishingiz mumkin."),
            ("coffee", "Nonushta",
             "Restoranda 8:30 dan 10:30 gacha beriladi. Shved stolidan tashqari shakshuka, omlet, sosiska "
             "va boshqa taomlarga buyurtma berishingiz mumkin — ular nonushtaga kiritilgan."),
            ("utensils", "Restoran va terassa",
             "Tushlik va kechki ovqat restoranda yoki tog' manzarali terassada. Menyu — menu.balandda.uz."),
            ("waves-ladder", "Basseyn va SPA",
             "Umumiy basseyn yozgi mavsumda isitiladi — mehmonlar uchun bepul. SPA muolajalari — oldindan yozilish orqali."),
            ("wifi", "Wi-Fi va TV",
             "Tezkor Wi-Fi butun hudud bo'ylab ishlaydi. Har bir televizorda oldindan to'langan obunali "
             "Netflix va ITV, shuningdek YouTube bor."),
            ("bed-double", "Uyingizda",
             "Qulay xalatlar, divanlar uchun zaxira choyshablar va gigiyena vositalari."),
            ("flame", "Oshxona va mangal",
             "Oshxona idish-tovoq bilan to'liq jihozlangan. Hovlida o'tin hamda mangal yoki qozon uchun "
             "barcha kerakli narsalar bor."),
        ],
        "links": "Foydali havolalar", "l_map": "Yo'nalish", "l_menu": "Restoran menyusi", "l_tg": "Telegram",
        "cancel": "Bronni bekor qilish va pulni qaytarish — ommaviy ofertaning 7-bo'limiga ko'ra: balandda.uz/offer.html",
        "see_you": "Tog'larda ko'rishguncha!",
    },
}


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


def fmt_date(lang: str, iso: str) -> str:
    try:
        d = date.fromisoformat(str(iso)[:10])
    except ValueError:
        return str(iso)
    m, w = MONTHS[lang][d.month - 1], WEEKDAYS[lang][d.weekday()]
    if lang == "en":
        return f"{w}, {d.day} {m} {d.year}"
    if lang == "ru":
        return f"{d.day} {m} {d.year}, {w}"
    return f"{d.day}-{m} {d.year}, {w}"


def _amounts(d: dict) -> tuple[float | None, float, float | None]:
    total = d.get("total_amount")
    total = float(total) if total not in (None, "") else None
    paid = float(d.get("paid_amount") or 0)
    bal = max(0.0, total - paid) if total is not None else None
    return total, paid, bal


# ───────────────────────── PDF ─────────────────────────

@lru_cache(maxsize=16)
def _hero_bytes(fname: str, focus: float, ratio: float) -> bytes:
    """Crop a square site photo to a wide band (w/h = ratio) around a vertical focus
    point and bake in the navy fade (top for the logo, bottom for the title)."""
    from PIL import Image
    im = Image.open(os.path.join(ASSETS, "img", fname)).convert("RGB")
    w, h = im.size
    ch = int(w / ratio)
    top = int(max(0, min(h - ch, focus * h - ch / 2)))
    im = im.crop((0, top, w, top + ch))
    shade = Image.new("RGB", im.size, NAVY_2)
    mask = Image.new("L", (1, ch))
    for yy in range(ch):
        f = yy / ch
        a = 0.38 * max(0.0, 1 - f / 0.28)                      # top fade behind the logo
        if f > 0.30:
            a = max(a, 0.9 * ((f - 0.30) / 0.70) ** 1.3)        # bottom fade behind the title
        mask.putpixel((0, yy), int(255 * min(a, 0.9)))
    im = Image.composite(shade, im, mask.resize(im.size))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=84)
    return buf.getvalue()


@lru_cache(maxsize=16)
def _band_bytes(fname: str, focus: float, ratio: float) -> bytes:
    from PIL import Image
    im = Image.open(os.path.join(ASSETS, "img", fname)).convert("RGB")
    w, h = im.size
    ch = int(w / ratio)
    if ch > h:
        cw = int(h * ratio)
        im = im.crop(((w - cw) // 2, 0, (w - cw) // 2 + cw, h))
    else:
        top = int(max(0, min(h - ch, focus * h - ch / 2)))
        im = im.crop((0, top, w, top + ch))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=82)
    return buf.getvalue()


class _Doc(FPDF):
    def __init__(self):
        super().__init__(orientation="P", unit="mm", format="A4")
        self.set_auto_page_break(False)
        self.set_margins(0, 0, 0)
        fd = os.path.join(ASSETS, "fonts")
        self.add_font("M", "", os.path.join(fd, "Montserrat_400Regular.ttf"))
        self.add_font("M", "B", os.path.join(fd, "Montserrat_700Bold.ttf"))
        self.add_font("MS", "", os.path.join(fd, "Montserrat_600SemiBold.ttf"))
        self.add_font("MM", "", os.path.join(fd, "Montserrat_500Medium.ttf"))
        self.set_title("Balandda Chimgan — voucher")
        self.set_author("Balandda Chimgan")

    def txt(self, x, y, s, size=10, font="M", style="", color=INK, w=0, h=None, align="L", link=""):
        self.set_font(font, style, size)
        self.set_text_color(*color)
        self.set_xy(x, y)
        self.cell(w, h or size * 0.45, s, align=align, link=link)

    def para(self, x, y, w, s, size=9, font="M", color=INK, lh=None) -> float:
        """multi_cell; returns the bottom y."""
        self.set_font(font, "", size)
        self.set_text_color(*color)
        self.set_xy(x, y)
        self.multi_cell(w, lh or size * 0.5, s, align="L")
        return self.get_y()

    def para_h(self, w, s, size=9, font="M", lh=None) -> float:
        self.set_font(font, "", size)
        lines = self.multi_cell(w, lh or size * 0.5, s, dry_run=True, output="LINES")
        return len(lines) * (lh or size * 0.5)

    def icon(self, name, x, y, size):
        p = os.path.join(ASSETS, "icons", f"{name}.svg")
        if os.path.exists(p):
            self.image(p, x=x, y=y, w=size, h=size)

    def rrect(self, x, y, w, h, r, fill, opacity=None):
        self.set_fill_color(*fill)
        if opacity is not None:
            with self.local_context(fill_opacity=opacity):
                self.rect(x, y, w, h, style="F", round_corners=True, corner_radius=r)
        else:
            self.rect(x, y, w, h, style="F", round_corners=True, corner_radius=r)


def build_voucher_pdf(lang: str, d: dict) -> bytes:
    """d: booking_id, guest_name, unit, check_in, check_out (ISO), guests, nights,
    paid_amount, total_amount, t_in, t_out, + optional: status, property_type,
    paid_card, guide (bool, default True)."""
    lg = norm_lang(lang)
    t = T[lg]
    total, paid, bal = _amounts(d)
    pending = (d.get("status") == "HOLD") or (paid <= 0 and d.get("status") != "CONFIRMED")
    nights = d.get("nights") or 0
    pdf = _Doc()
    W, M = 210, 16

    # ═════════ Page 1 — voucher ═════════
    pdf.add_page()
    pdf.set_fill_color(*WHITE)
    pdf.rect(0, 0, W, 297, style="F")

    # Hero photo with a navy fade at the bottom
    HERO = 86
    fname, focus = PHOTO.get(d.get("property_type") or "", PHOTO_DEFAULT)
    try:
        pdf.image(io.BytesIO(_hero_bytes(fname, focus, W / HERO)), x=0, y=0, w=W, h=HERO)
    except Exception:
        pdf.set_fill_color(*NAVY)
        pdf.rect(0, 0, W, HERO, style="F")
    pdf.image(os.path.join(ASSETS, "img", "balandda_logo_white.png"), x=M, y=9, w=46)
    pdf.txt(W - M - 60, 11, CONTACT["site"], 9, "MM", color=WHITE, w=60, align="R")

    # Status pill
    pill = t["pending"] if pending else t["confirmed"]
    pdf.set_font("M", "B", 8)
    pw = pdf.get_string_width(pill) + 10
    pdf.rrect(M, 46, pw, 7.5, 3.7, (255, 196, 61) if pending else LIME)
    pdf.txt(M, 47.6, pill, 8, "M", "B", NAVY_2, w=pw, align="C")
    pdf.txt(M, 57, t["booking"].format(id=d["booking_id"]), 25, "M", "B", WHITE)
    sub = f"{d.get('unit') or ''}  ·  {t['nights_n'](nights)}" if nights else (d.get("unit") or "")
    pdf.txt(M, 72, sub, 12, "MM", color=(214, 230, 238))

    # Greeting
    y = HERO + 9
    pdf.txt(M, y, t["dear"].format(name=d.get("guest_name") or ""), 12, "M", "B", INK)
    y = pdf.para(M, y + 7, W - 2 * M, t["intro_pending"] if pending else t["intro"], 9.5, color=GREY, lh=5)

    # Check-in / check-out cards
    y += 6
    cw, ch, gap = 76, 27, W - 2 * M - 2 * 76
    for i, (lab, iso, tt, ico) in enumerate((
        (t["checkin"], d["check_in"], t["from"].format(t=d.get("t_in") or "14:00"), "log-in"),
        (t["checkout"], d["check_out"], t["until"].format(t=d.get("t_out") or "12:00"), "log-out"),
    )):
        x = M + i * (cw + gap)
        pdf.rrect(x, y, cw, ch, 3, PAPER)
        pdf.icon(ico, x + 5, y + 5, 4.2)
        pdf.txt(x + 11, y + 5.4, lab, 7.5, "MS", color=BLUE)
        pdf.txt(x + 5, y + 12, fmt_date(lg, iso), 12, "M", "B", INK)
        pdf.txt(x + 5, y + 19.5, tt, 9.5, "MM", color=GREY)
    # nights badge between the cards
    cx = M + cw + gap / 2
    pdf.set_fill_color(*NAVY)
    pdf.ellipse(cx - 9, y + ch / 2 - 9, 18, 18, style="F")
    pdf.txt(cx - 9, y + ch / 2 - 4.6, str(nights or "—"), 13, "M", "B", WHITE, w=18, align="C")
    nl = t["nights_n"](nights).split(" ", 1)[-1] if nights else ""
    pdf.txt(cx - 9, y + ch / 2 + 1.6, nl, 6, "MS", color=LIME, w=18, align="C")
    y += ch + 8

    # Guest / unit / guests
    cols = [(t["guest"], d.get("guest_name") or "—", 74),
            (t["unit"], d.get("unit") or "—", 66)]
    if d.get("guests"):
        cols.append((t["guests"], str(d["guests"]), 38))
    x = M
    for lab, val, w in cols:
        pdf.txt(x, y, lab, 7, "MS", color=GREY)
        pdf.set_font("M", "B", 10.5)
        v = val
        while pdf.get_string_width(v) > w - 3 and len(v) > 4:
            v = v[:-2]
        pdf.txt(x, y + 4.5, v if v == val else v + "…", 10.5, "M", "B", INK)
        x += w
    y += 14

    # Payment summary
    pdf.rrect(M, y, W - 2 * M, 23, 3, NAVY)
    cells = []
    if total is not None:
        cells.append((t["total"], f"{_fmt_sum(total)} {t['uzs']}", WHITE))
    cells.append((t["paid"], f"{_fmt_sum(paid)} {t['uzs']}" if paid > 0 else t["not_paid"],
                  LIME if paid > 0 else (255, 196, 61)))
    if bal is not None:
        cells.append((t["balance"], f"{_fmt_sum(bal)} {t['uzs']}" if bal > 0 else t["paid_full"],
                      WHITE if bal > 0 else LIME))
    cwid = (W - 2 * M) / len(cells)
    for i, (lab, val, col) in enumerate(cells):
        x = M + i * cwid
        if i:
            pdf.set_draw_color(70, 88, 100)
            pdf.set_line_width(0.2)
            pdf.line(x, y + 5, x, y + 18)
        pdf.txt(x + 7, y + 5.5, lab, 8, "MM", color=(170, 190, 200))
        pdf.txt(x + 7, y + 11.5, val, 12.5, "M", "B", col)
    if d.get("paid_card"):
        pdf.txt(M, y + 24.5, f"{d['paid_card']}", 7, "M", color=GREY)
    y += 31

    # Getting here + before you arrive (text left, QR right)
    qr = 26
    tw = W - 2 * M - qr - 10
    for ico, title, body, qrf, cap, extra, link in (
        ("map-pin", t["getting"], t["getting_txt"], "map.png", t["scan_map"], ADDRESS[lg], CONTACT["map_url"]),
        ("phone", t["before"], t["before_txt"], "telegram.png", t["scan_tg"],
         "  ·  ".join(x for x in (CONTACT["phone"], CONTACT["telegram"], CONTACT["hours"]) if x),
         CONTACT["telegram_url"]),
    ):
        y0 = y
        pdf.icon(ico, M, y0 + 0.2, 4.6)
        pdf.txt(M + 7, y0 + 0.6, title, 11, "M", "B", INK)
        yb = pdf.para(M, y0 + 7.5, tw, body, 9, color=INK, lh=4.6)
        yb = pdf.para(M, yb + 1.2, tw, extra, 8.5, "MS", color=BLUE if ico == "phone" else GREY, lh=4.4)
        pdf.image(os.path.join(ASSETS, "qr", qrf), x=W - M - qr, y=y0, w=qr, h=qr, link=link)
        pdf.txt(W - M - qr - 4, y0 + qr + 1.2, cap, 6.8, "MM", color=GREY, w=qr + 8, align="C")
        y = max(yb, y0 + qr + 5) + 6

    # Footer band
    fy = 297 - 25
    pdf.set_fill_color(*NAVY_2)
    pdf.rect(0, fy, W, 25, style="F")
    pdf.txt(M, fy + 6, t["show"], 10, "M", "B", WHITE)
    pdf.txt(M, fy + 12.5,
            f"{CONTACT['phone']}  ·  {CONTACT['telegram']}  ·  {CONTACT['email']}  ·  {CONTACT['site']}",
            8.5, "MM", color=(170, 200, 214))
    pdf.txt(M, fy + 17.6, t["valid"], 7, "M", color=(120, 145, 158))

    # ═════════ Page 2 — stay guide (accommodation only) ═════════
    if d.get("guide", True):
        pdf.add_page()
        pdf.set_fill_color(*NAVY)
        pdf.rect(0, 0, W, 36, style="F")
        pdf.image(os.path.join(ASSETS, "img", "balandda_logo_white.png"), x=W - M - 38, y=13, w=38)
        pdf.txt(M, 11, t["stay_title"], 19, "M", "B", WHITE)
        pdf.txt(M, 22, t["stay_sub"], 9, "MM", color=(190, 210, 220))
        pdf.set_fill_color(*LIME)
        pdf.rect(0, 36, W, 1.4, style="F")

        y = 47
        colw, cgap = (W - 2 * M - 8) / 2, 8
        guide = t["guide"]
        for r in range(0, len(guide), 2):
            pair = guide[r:r + 2]
            hs = [pdf.para_h(colw - 16, body, 8.8, lh=4.5) for _, _, body in pair]
            rh = max(hs) + 13
            for c, (ico, title, body) in enumerate(pair):
                x = M + c * (colw + cgap)
                pdf.rrect(x, y, colw, rh, 3, PAPER)
                pdf.set_fill_color(*BLUE_XL)
                pdf.ellipse(x + 4.5, y + 4.5, 9, 9, style="F")
                pdf.icon(ico, x + 6.25, y + 6.25, 5.5)
                pdf.txt(x + 16, y + 5.6, title, 10.5, "M", "B", INK)
                pdf.para(x + 16, y + 11, colw - 20, body, 8.8, color=(60, 72, 80), lh=4.5)
            y += rh + 5

        # Useful links with QR codes
        y += 2
        pdf.txt(M, y, t["links"], 11, "M", "B", INK)
        y += 7
        q, lw = 20, (W - 2 * M) / 3
        for i, (qrf, lab, url, shown) in enumerate((
            ("map.png", t["l_map"], CONTACT["map_url"], "Google Maps"),
            ("menu.png", t["l_menu"], CONTACT["menu_url"], CONTACT["menu"]),
            ("telegram.png", t["l_tg"], CONTACT["telegram_url"], CONTACT["telegram"]),
        )):
            x = M + i * lw
            pdf.image(os.path.join(ASSETS, "qr", qrf), x=x, y=y, w=q, h=q, link=url)
            pdf.txt(x + q + 3.5, y + 5.5, lab, 9, "M", "B", INK)
            pdf.txt(x + q + 3.5, y + 10.5, shown, 7.5, "MM", color=BLUE, link=url)
        y += q + 8

        # Photo band to close the page (fills whatever room the guide left)
        fy = 297 - 22
        band = fy - 8 - y
        if band > 25:
            try:
                bf, bfoc = ("chalet_03.jpg", 0.5) if fname == "villa_1.jpg" else ("villa_1.jpg", 0.74)
                pdf.image(io.BytesIO(_band_bytes(bf, bfoc, (W - 2 * M) / band)),
                          x=M, y=y, w=W - 2 * M, h=band)
            except Exception:
                pass

        pdf.set_draw_color(*LINE)
        pdf.set_line_width(0.3)
        pdf.line(M, fy - 4, W - M, fy - 4)
        pdf.para(M, fy, W - 2 * M - 50, t["cancel"], 7.8, color=GREY, lh=4)
        pdf.txt(W - M - 60, fy + 1, t["see_you"], 11, "M", "B", NAVY, w=60, align="R")

    return bytes(pdf.output())


# ───────────────────────── E-mail ─────────────────────────

SUBJ = {
    "ru": "Бронь №{id} подтверждена — Balandda Chimgan",
    "uz": "Bron №{id} tasdiqlandi — Balandda Chimgan",
    "en": "Booking #{id} confirmed — Balandda Chimgan",
}
SUBJ_PENDING = {
    "ru": "Бронь №{id} — Balandda Chimgan",
    "uz": "Bron №{id} — Balandda Chimgan",
    "en": "Booking #{id} — Balandda Chimgan",
}
E = {
    "en": {"attached": "Your voucher is attached (PDF) — show it at check-in; a phone screen is fine.",
           "btn_map": "Directions", "btn_tg": "Message reception", "btn_menu": "Menu",
           "team": "Balandda team", "questions": "Questions or changes"},
    "ru": {"attached": "Ваучер во вложении (PDF) — покажите его при заселении, можно с экрана телефона.",
           "btn_map": "Маршрут", "btn_tg": "Написать на ресепшн", "btn_menu": "Меню",
           "team": "Команда Balandda", "questions": "Вопросы и изменения брони"},
    "uz": {"attached": "Vaucher ilova qilingan (PDF) — joylashishda ko'rsating, telefon ekranidan ham bo'ladi.",
           "btn_map": "Yo'nalish", "btn_tg": "Resepshnga yozing", "btn_menu": "Menyu",
           "team": "Balandda jamoasi", "questions": "Savollar va bronni o'zgartirish"},
}
SITE_IMG = "https://www.balandda.uz/assets/img/"
EMAIL_PHOTO = {"CHALET_WITH_SAUNA": "chalet_03.jpg", "CHALET_WITHOUT_SAUNA": "chalet_03.jpg",
               "WHITE_CHALET": "chalet_01.jpg", "APARTMENT": "apart_1.jpg", "PENTHOUSE": "pent_1.jpg",
               "VILLA": "villa_1.jpg", "SPA_SUITE": "spa_01.jpg"}


def _pending(d: dict) -> bool:
    _, paid, _ = _amounts(d)
    return (d.get("status") == "HOLD") or (paid <= 0 and d.get("status") != "CONFIRMED")


def _subject(lg: str, d: dict) -> str:
    return (SUBJ_PENDING if _pending(d) else SUBJ)[lg].format(id=d["booking_id"])


def build_email(lang: str, d: dict) -> tuple[str, str]:
    """(subject, plain-text body) — also the text/plain part of the HTML e-mail."""
    lg = norm_lang(lang)
    t, e = T[lg], E[lg]
    total, paid, bal = _amounts(d)
    lines = [t["dear"].format(name=d.get("guest_name") or ""), "",
             t["intro_pending"] if _pending(d) else t["intro"], e["attached"], "",
             f"{t['booking'].format(id=d['booking_id'])} · {d.get('unit') or ''}",
             f"{t['checkin'].title()}: {fmt_date(lg, d['check_in'])}, {t['from'].format(t=d.get('t_in'))}",
             f"{t['checkout'].title()}: {fmt_date(lg, d['check_out'])}, {t['until'].format(t=d.get('t_out'))}"]
    if total is not None:
        lines.append(f"{t['total']}: {_fmt_sum(total)} {t['uzs']}")
    lines.append(f"{t['paid']}: {_fmt_sum(paid)} {t['uzs']}" if paid > 0 else f"{t['paid']}: {t['not_paid']}")
    if bal:
        lines.append(f"{t['balance']}: {_fmt_sum(bal)} {t['uzs']}")
    lines += ["", f"{t['getting']}: {t['getting_txt']}", f"{ADDRESS[lg]} — {CONTACT['map_url']}", "",
              f"{t['before']}: {t['before_txt']}",
              f"{CONTACT['phone']} · {CONTACT['telegram_url']} · {CONTACT['email']}", "",
              f"{t['cancel']}", "", t["see_you"], f"— {e['team']} · {CONTACT['site']}"]
    return _subject(lg, d), "\n".join(lines)


def build_email_html(lang: str, d: dict) -> str:
    from html import escape as h
    lg = norm_lang(lang)
    t, e = T[lg], E[lg]
    total, paid, bal = _amounts(d)
    pending = _pending(d)
    photo = SITE_IMG + EMAIL_PHOTO.get(d.get("property_type") or "", "villa_1.jpg")
    navy, blue, lime, grey = "#23333f", "#00a7e1", "#cadb44", "#6e7c84"
    font = "font-family:Montserrat,Segoe UI,Helvetica,Arial,sans-serif;"
    pill_bg = "#ffc43d" if pending else lime

    def money_row(label, value, color="#171d29", bold=True):
        return (f'<tr><td style="{font}padding:4px 0;color:{grey};font-size:14px">{h(label)}</td>'
                f'<td align="right" style="{font}padding:4px 0;color:{color};font-size:15px;'
                f'font-weight:{700 if bold else 500}">{h(value)}</td></tr>')

    rows = ""
    if total is not None:
        rows += money_row(t["total"], f"{_fmt_sum(total)} {t['uzs']}")
    rows += money_row(t["paid"], f"{_fmt_sum(paid)} {t['uzs']}" if paid > 0 else t["not_paid"],
                      "#24854a" if paid > 0 else "#c47800")
    if bal is not None:
        rows += money_row(t["balance"], f"{_fmt_sum(bal)} {t['uzs']}" if bal > 0 else t["paid_full"],
                          "#171d29" if bal > 0 else "#24854a")

    def btn(label, url, bg, fg):
        return (f'<a href="{url}" style="{font}display:inline-block;background:{bg};color:{fg};'
                f'text-decoration:none;font-weight:700;font-size:14px;padding:11px 18px;border-radius:8px;'
                f'margin:4px 6px 4px 0">{h(label)}</a>')

    guide = "".join(
        f'<tr><td style="{font}padding:7px 0;font-size:13.5px;color:#3c4850;line-height:1.5">'
        f'<b style="color:#171d29">{h(title)}.</b> {h(body)}</td></tr>'
        for _, title, body in t["guide"]) if d.get("guide", True) else ""

    return f"""<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{h(_subject(lg, d))}</title></head>
<body style="margin:0;padding:0;background:#eef2f4">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#eef2f4"><tr><td align="center" style="padding:24px 12px">
<table role="presentation" width="600" cellpadding="0" cellspacing="0" style="max-width:600px;width:100%;background:#ffffff;border-radius:14px;overflow:hidden">
<tr><td style="background:{navy};padding:18px 28px">
  <img src="{SITE_IMG.replace('/img/', '/logo/')}balandda_logo_white.png" width="150" alt="Balandda Chimgan" style="display:block;border:0">
</td></tr>
<tr><td><img src="{photo}" width="600" alt="" style="display:block;width:100%;max-height:260px;object-fit:cover;border:0"></td></tr>
<tr><td style="padding:26px 28px 6px">
  <span style="{font}display:inline-block;background:{pill_bg};color:#122733;font-size:11px;font-weight:700;letter-spacing:.06em;padding:5px 12px;border-radius:20px">{h(t['pending'] if pending else t['confirmed'])}</span>
  <h1 style="{font}margin:14px 0 4px;font-size:26px;color:#171d29">{h(t['booking'].format(id=d['booking_id']))}</h1>
  <p style="{font}margin:0;font-size:15px;color:{grey}">{h(d.get('unit') or '')} · {h(t['nights_n'](d.get('nights') or 0))}</p>
  <p style="{font}margin:20px 0 6px;font-size:15px;color:#171d29;font-weight:700">{h(t['dear'].format(name=d.get('guest_name') or ''))}</p>
  <p style="{font}margin:0 0 6px;font-size:14.5px;line-height:1.55;color:#3c4850">{h(t['intro_pending'] if pending else t['intro'])}</p>
  <p style="{font}margin:0;font-size:13.5px;line-height:1.5;color:{grey}">{h(e['attached'])}</p>
</td></tr>
<tr><td style="padding:16px 28px">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f4f7f8;border-radius:10px"><tr>
    <td width="50%" style="{font}padding:14px 16px;vertical-align:top">
      <div style="font-size:11px;font-weight:600;color:{blue};letter-spacing:.05em">{h(t['checkin'])}</div>
      <div style="font-size:16px;font-weight:700;color:#171d29;margin-top:4px">{h(fmt_date(lg, d['check_in']))}</div>
      <div style="font-size:13px;color:{grey};margin-top:2px">{h(t['from'].format(t=d.get('t_in')))}</div></td>
    <td width="50%" style="{font}padding:14px 16px;vertical-align:top;border-left:1px solid #dee5e9">
      <div style="font-size:11px;font-weight:600;color:{blue};letter-spacing:.05em">{h(t['checkout'])}</div>
      <div style="font-size:16px;font-weight:700;color:#171d29;margin-top:4px">{h(fmt_date(lg, d['check_out']))}</div>
      <div style="font-size:13px;color:{grey};margin-top:2px">{h(t['until'].format(t=d.get('t_out')))}</div></td>
  </tr></table>
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin-top:12px">{rows}</table>
</td></tr>
<tr><td style="padding:6px 28px 4px">
  <h2 style="{font}font-size:16px;margin:10px 0 6px;color:#171d29">{h(t['getting'])}</h2>
  <p style="{font}margin:0 0 4px;font-size:14px;line-height:1.55;color:#3c4850">{h(t['getting_txt'])}</p>
  <p style="{font}margin:0 0 10px;font-size:13px;color:{grey}">{h(ADDRESS[lg])}</p>
  <h2 style="{font}font-size:16px;margin:14px 0 6px;color:#171d29">{h(t['before'])}</h2>
  <p style="{font}margin:0 0 4px;font-size:14px;line-height:1.55;color:#3c4850">{h(t['before_txt'])}</p>
  <p style="{font}margin:0 0 10px;font-size:14px;font-weight:600"><a href="tel:{CONTACT['phone_tel']}" style="color:{blue};text-decoration:none">{CONTACT['phone']}</a> <span style="color:{grey};font-weight:400">· <a href="{CONTACT['telegram_url']}" style="color:{blue};text-decoration:none">{CONTACT['telegram']}</a></span></p>
  {btn(e['btn_map'], CONTACT['map_url'], blue, '#ffffff')}{btn(e['btn_tg'], CONTACT['telegram_url'], navy, '#ffffff')}{btn(e['btn_menu'], CONTACT['menu_url'], lime, '#122733')}
</td></tr>
{f'<tr><td style="padding:14px 28px 6px"><h2 style="{font}font-size:16px;margin:8px 0 4px;color:#171d29">{h(t["stay_title"])}</h2><table role="presentation" width="100%" cellpadding="0" cellspacing="0">{guide}</table></td></tr>' if guide else ''}
<tr><td style="padding:16px 28px 26px">
  <p style="{font}margin:0 0 12px;font-size:12.5px;line-height:1.5;color:{grey}">{h(t['cancel'])}</p>
  <p style="{font}margin:0;font-size:15px;font-weight:700;color:{navy}">{h(t['see_you'])}</p>
  <p style="{font}margin:2px 0 0;font-size:13px;color:{grey}">— {h(e['team'])}</p>
</td></tr>
<tr><td style="background:#122733;padding:16px 28px">
  <p style="{font}margin:0;font-size:12px;line-height:1.6;color:#aac8d6">{CONTACT['phone']} · <a href="{CONTACT['telegram_url']}" style="color:#aac8d6">{CONTACT['telegram']}</a> · <a href="mailto:{CONTACT['email']}" style="color:#aac8d6">{CONTACT['email']}</a> · <a href="https://www.balandda.uz" style="color:#aac8d6">{CONTACT['site']}</a></p>
</td></tr>
</table></td></tr></table></body></html>"""


def build_cancel_email(d: dict) -> tuple[str, str]:
    """Cancellation notice, RU + EN in one plain-text message (the booking has no
    stored language, so both languages always go out)."""
    subject = f"Бронь №{d['booking_id']} отменена — Balandda Chimgan / Booking cancelled"
    name = d.get("guest_name") or ""
    unit = d.get("unit") or ""
    body = (
        f"Здравствуйте, {name}!\n\n"
        f"Ваша бронь №{d['booking_id']} — {unit}, {d['check_in']} → {d['check_out']} — отменена.\n"
        "Если это произошло по ошибке или вы хотите выбрать другие даты, просто ответьте на это письмо "
        "или свяжитесь с оператором: +998 90 007 70 77 (Telegram/телефон).\n"
        "По вопросам внесённой предоплаты также обращайтесь к оператору.\n\n"
        "— — —\n\n"
        f"Hello {name}!\n\n"
        f"Your booking #{d['booking_id']} — {unit}, {d['check_in']} → {d['check_out']} — has been cancelled.\n"
        "If this was a mistake or you would like different dates, just reply to this e-mail "
        "or contact our operator: +998 90 007 70 77 (Telegram/phone).\n"
        "For questions about a prepayment you made, please also contact the operator.\n\n"
        "Balandda Chimgan · balandda.uz · info@balandda.uz"
    )
    return subject, body


# ───────────────────────── data ─────────────────────────

EN_TYPE_NAME = {
    "CHALET_WITH_SAUNA": "Chalet {n}", "CHALET_WITHOUT_SAUNA": "Chalet {n}",
    "WHITE_CHALET": "White Chalet {n}", "APARTMENT": "Apartment {n}",
    "PENTHOUSE": "Penthouse", "VILLA": "Villa Infinity", "SPA_SUITE": "SPA Suite {n}",
}


def unit_name(prop, lang: str) -> str:
    if prop is None:
        return ""
    lg = norm_lang(lang)
    if lg == "en":
        if getattr(prop, "name_en", None):
            return prop.name_en
        # Catalog has no English names yet: derive from the unit type + number.
        import re as _re
        ptype = getattr(getattr(prop, "property_type", None), "value", None)
        tpl = EN_TYPE_NAME.get(ptype or "")
        if tpl:
            m = _re.search(r"\d+", prop.name_ru or "")
            return tpl.format(n=m.group(0) if m else "").strip()
    if lg == "uz" and getattr(prop, "name_uz", None):
        return prop.name_uz
    return prop.name_ru or ""


async def load_voucher_data(session, res, lang: str, paid_card: str | None = None) -> dict:
    """Voucher dict for a reservation, straight from the DB. "Paid" follows the
    calendar's rule: the payment ledger, falling back to legacy deposit_amount."""
    from sqlalchemy import func, select
    from db.models import IncomeEntry, Property

    prop = await session.get(Property, res.property_id)
    income = (await session.execute(
        select(func.coalesce(func.sum(IncomeEntry.amount), 0)).where(IncomeEntry.reservation_id == res.id)
    )).scalar() or 0
    income = float(income)
    paid = income if income > 0 else float(res.deposit_amount or 0)
    ptype = prop.property_type.value if prop is not None and prop.property_type else None
    t_in, t_out = checkin_times(ptype)
    bu = getattr(getattr(prop, "business_unit", None), "value", None)
    status = getattr(res.status, "value", res.status)
    return {
        "booking_id": res.id,
        "guest_name": res.guest_name,
        "unit": unit_name(prop, lang),
        "property_type": ptype,
        "check_in": res.check_in.isoformat(),
        "check_out": res.check_out.isoformat(),
        "guests": res.guest_count,
        "nights": (res.check_out - res.check_in).days,
        "paid_amount": paid,
        "paid_card": paid_card,
        "total_amount": float(res.total_amount) if res.total_amount is not None else None,
        "t_in": t_in, "t_out": t_out,
        "status": status,
        "guide": bu != "RESTAURANT",
    }
