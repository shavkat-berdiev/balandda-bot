from bot.locales import ru, uz

_locales = {
    "ru": ru.messages,
    "uz": uz.messages,
}


def get_text(key: str, lang: str = "ru", **kwargs) -> str:
    """Get localized text by key. Falls back to Russian if key not found."""
    messages = _locales.get(lang, _locales["ru"])
    text = messages.get(key, _locales["ru"].get(key, key))
    if kwargs:
        try:
            return text.format(**kwargs)
        except (KeyError, ValueError):
            return text
    return text
