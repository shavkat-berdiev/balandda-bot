"""Tests for the CardXabar message parser (real samples from 26.07.2026)."""

from bot.card_parser import parse_cardxabar_message

SAMPLE_IN = """🟢 Perevod na kartu
➕ 400 000.00 UZS
💳 ***4042
📍 AO PAYNET, UZ
🕓 26.07.26 00:24
💵 63 612 380.90 UZS"""

SAMPLE_OUT = """🔴 E-Com oplata
➖ 29 750.00 UZS
💳 ***4042
📍 OOO UZUM MARKET, UZ
🕓 26.07.26 15:15
💵 62 543 777.62 UZS"""

SAMPLE_CLICK = """🟢 Perevod na kartu
➕ 540 000.00 UZS
💳 ***4042
📍 CLICK P2P H2UEW, UZ
🕓 26.07.26 15:37
💵 63 083 777.62 UZS"""


def test_parse_incoming():
    p = parse_cardxabar_message(SAMPLE_IN)
    assert p is not None
    assert p.direction == "IN"
    assert p.tx_type == "Perevod na kartu"
    assert p.amount == 400000.0
    assert p.card_last4 == "4042"
    assert p.merchant == "AO PAYNET, UZ"
    assert (p.tx_time.year, p.tx_time.month, p.tx_time.day) == (2026, 7, 26)
    assert (p.tx_time.hour, p.tx_time.minute) == (0, 24)
    assert p.balance_after == 63612380.90


def test_parse_outgoing():
    p = parse_cardxabar_message(SAMPLE_OUT)
    assert p is not None
    assert p.direction == "OUT"
    assert p.tx_type == "E-Com oplata"
    assert p.amount == 29750.0


def test_parse_click_p2p():
    p = parse_cardxabar_message(SAMPLE_CLICK)
    assert p is not None
    assert p.direction == "IN"
    assert p.amount == 540000.0


def test_parse_nbsp_amounts():
    text = SAMPLE_IN.replace(" 000.00", " 000.00")
    p = parse_cardxabar_message(text)
    assert p is not None
    assert p.amount == 400000.0


def test_non_transaction_message():
    assert parse_cardxabar_message("Здравствуйте! Ваш баланс ...") is None
    assert parse_cardxabar_message("") is None
