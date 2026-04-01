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


def main_menu_keyboard(lang: str = "ru") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text=f"📝 {get_text('btn_new_report', lang)}",
                callback_data="action:new_report",
            ),
        ],
        [
            InlineKeyboardButton(
                text=f"💰 {get_text('btn_cash_in', lang)}",
                callback_data="action:cash_in",
            ),
            InlineKeyboardButton(
                text=f"💸 {get_text('btn_cash_out', lang)}",
                callback_data="action:cash_out",
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
            InlineKeyboardButton(
                text=f"⚙️ {get_text('btn_settings', lang)}",
                callback_data="action:settings",
            ),
        ],
    ])


def confirm_keyboard(lang: str = "ru") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text=f"✅ {get_text('btn_confirm', lang)}",
                callback_data="confirm:yes",
            ),
            InlineKeyboardButton(
                text=f"❌ {get_text('btn_cancel', lang)}",
                callback_data="confirm:no",
            ),
        ]
    ])


def language_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🇷🇺 Русский", callback_data="lang:ru"),
            InlineKeyboardButton(text="🇺🇿 O'zbek", callback_data="lang:uz"),
        ]
    ])
