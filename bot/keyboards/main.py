from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot.locales import get_text

# All business sections — add new ones here
SECTIONS = [
    ("resort", "section_resort"),
    ("restaurant", "section_restaurant"),
    ("xush", "section_xush"),
]


def section_keyboard(lang: str = "ru") -> InlineKeyboardMarkup:
    buttons = []
    for code, label_key in SECTIONS:
        buttons.append([InlineKeyboardButton(
            text=get_text(label_key, lang),
            callback_data=f"section:{code}",
        )])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def main_menu_keyboard(lang: str = "ru", current_section: str = "resort", role: str = "") -> InlineKeyboardMarkup:
    # Build switch-section buttons — show all OTHER sections
    switch_buttons = []
    for code, label_key in SECTIONS:
        if code != current_section:
            switch_buttons.append(InlineKeyboardButton(
                text=f"🔄 {get_text(label_key, lang)}",
                callback_data=f"section:{code}",
            ))

    # PURCHASER role — restricted menu: only purchase + wallet
    if role == "PURCHASER":
        return InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🛒 Закуп",
                    callback_data="action:purchase",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="💼 Инкассация",
                    callback_data="action:wallet",
                ),
            ],
            switch_buttons,
            [
                InlineKeyboardButton(
                    text=f"⚙️ {get_text('btn_settings', lang)}",
                    callback_data="action:settings",
                ),
            ],
        ])

    # Full menu for all other roles
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text=f"📝 {get_text('btn_new_report', lang)}",
                callback_data="action:new_report",
            ),
            InlineKeyboardButton(
                text="🛒 Закуп",
                callback_data="action:purchase",
            ),
        ],
        [
            InlineKeyboardButton(
                text=f"💵 {get_text('btn_prepayment', lang)}",
                callback_data="action:prepayment",
            ),
            InlineKeyboardButton(
                text="💼 Инкассация",
                callback_data="action:wallet",
            ),
        ],
        [
            InlineKeyboardButton(
                text=f"📋 {get_text('btn_history', lang)}",
                callback_data="action:history",
            ),
            InlineKeyboardButton(
                text=f"📊 {get_text('btn_report', lang)}",
                callback_data="action:report",
            ),
        ],
        switch_buttons,
        [
            InlineKeyboardButton(
                text=f"⚙️ {get_text('btn_settings', lang)}",
                callback_data="action:settings",
            ),
        ],
    ])


def language_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🇷🇺 Русский", callback_data="lang:ru"),
            InlineKeyboardButton(text="🇺🇿 O'zbek", callback_data="lang:uz"),
        ]
    ])
