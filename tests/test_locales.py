"""Basic tests for the localization system."""

from bot.locales import get_text
from bot.locales import ru, uz


def test_all_keys_match():
    """Ensure Russian and Uzbek have the same keys."""
    ru_keys = set(ru.messages.keys())
    uz_keys = set(uz.messages.keys())
    missing_in_uz = ru_keys - uz_keys
    missing_in_ru = uz_keys - ru_keys
    assert not missing_in_uz, f"Keys missing in Uzbek: {missing_in_uz}"
    assert not missing_in_ru, f"Keys missing in Russian: {missing_in_ru}"


def test_get_text_russian():
    text = get_text("btn_cash_in", "ru")
    assert text == "Приход"


def test_get_text_uzbek():
    text = get_text("btn_cash_in", "uz")
    assert text == "Kirim"


def test_get_text_with_params():
    text = get_text("switched_to", "ru", section="Курорт")
    assert "Курорт" in text


def test_get_text_fallback():
    """Unknown lang falls back to Russian."""
    text = get_text("btn_cash_in", "xx")
    assert text == "Приход"


def test_get_text_missing_key():
    """Missing key returns key itself."""
    text = get_text("nonexistent_key", "ru")
    assert text == "nonexistent_key"
