"""Parser for CardXabar (UZCARD) transaction messages.

Message format (lines may vary slightly; whitespace can include NBSP):

    🟢 Perevod na kartu
    ➕ 400 000.00 UZS
    💳 ***4042
    📍 AO PAYNET, UZ
    🕓 26.07.26 00:24
    💵 63 612 380.90 UZS

🟢/➕ = incoming, 🔴/➖ = outgoing. 🕓 is local (Asia/Tashkent) time,
year is two-digit. 💵 is the card balance after the transaction.
"""

import logging
import re
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

_TZ = ZoneInfo("Asia/Tashkent")

# All space-like chars that may appear inside amounts (regular, NBSP, narrow NBSP, thin)
_SPACES = " \u00a0\u202f\u2009\u2007"
_AMOUNT_RE = re.compile(rf"([\d{_SPACES}]+(?:[.,]\d{{1,2}})?)\s*UZS", re.IGNORECASE)
_CARD_RE = re.compile(r"\*+\s*(\d{4})")
_TIME_RE = re.compile(r"(\d{2})\.(\d{2})\.(\d{2,4})\s+(\d{1,2}):(\d{2})")


@dataclass
class ParsedCardTx:
    direction: str          # "IN" | "OUT"
    tx_type: str | None
    amount: float
    card_last4: str
    merchant: str | None
    tx_time: datetime
    balance_after: float | None
    raw_text: str


def _parse_amount(s: str) -> float | None:
    m = _AMOUNT_RE.search(s)
    if not m:
        return None
    num = m.group(1)
    for ch in _SPACES:
        num = num.replace(ch, "")
    num = num.replace(",", ".")
    # Guard against grouped dots (e.g. "3.200.000") — keep only the last as decimal
    if num.count(".") > 1:
        whole, _, frac = num.rpartition(".")
        num = whole.replace(".", "") + "." + frac
    try:
        return float(num)
    except ValueError:
        return None


def parse_cardxabar_message(text: str) -> ParsedCardTx | None:
    """Parse one CardXabar message; None if it isn't a transaction message."""
    if not text:
        return None

    direction: str | None = None
    tx_type: str | None = None
    amount: float | None = None
    card_last4: str | None = None
    merchant: str | None = None
    tx_time: datetime | None = None
    balance_after: float | None = None

    for line in (l.strip() for l in text.splitlines() if l.strip()):
        if line.startswith("🟢") or line.startswith("🔴"):
            direction = "IN" if line.startswith("🟢") else "OUT"
            tx_type = line[1:].strip() or None
        elif line.startswith("➕") or line.startswith("➖"):
            if direction is None:
                direction = "IN" if line.startswith("➕") else "OUT"
            amount = _parse_amount(line)
        elif line.startswith("💳"):
            m = _CARD_RE.search(line)
            if m:
                card_last4 = m.group(1)
        elif line.startswith("📍"):
            merchant = line[1:].strip() or None
        elif line.startswith("🕓") or line.startswith("🕒") or line.startswith("🕐"):
            m = _TIME_RE.search(line)
            if m:
                day, month, year, hour, minute = (int(g) for g in m.groups())
                if year < 100:
                    year += 2000
                try:
                    tx_time = datetime(year, month, day, hour, minute, tzinfo=_TZ)
                except ValueError:
                    tx_time = None
        elif line.startswith("💵"):
            balance_after = _parse_amount(line)

    if direction is None or amount is None or card_last4 is None or tx_time is None:
        return None

    return ParsedCardTx(
        direction=direction,
        tx_type=tx_type,
        amount=amount,
        card_last4=card_last4,
        merchant=merchant,
        tx_time=tx_time,
        balance_after=balance_after,
        raw_text=text,
    )
