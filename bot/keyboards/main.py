from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot.locales import get_text


def section_keyboard(lang: str = "ru") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text=get_text("section_resort", lang),
                callback_data="section:resort",
            ),
            InlineKeyboardButton(
                text=get_text("section_restaurant", lang),
                callback_data="section:restaurant",
            ),
        ]
    ])


def main_menu_keyboard(lang: str = "ru", current_section: str = "resort", role: str = "") -> InlineKeyboardMarkup:
    # Determine the other section for the switch button
    if current_section == "resort":
        switch_label = f"🔄 {get_text('section_restaurant', lang)}"
        switch_data = "section:restaurant"
    else:
        switch_label = f"🔄 {get_text('section_resort', lang)}"
        switch_data = "section:resort"

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
            [
                InlineKeyboardButton(text=switch_label, callback_data=switch_data),
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
        [
            InlineKeyboardButton(text=switch_label, callback_data=switch_data),
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
