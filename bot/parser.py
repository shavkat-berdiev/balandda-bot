"""Parser for daily resort reports forwarded via Telegram.

Handles the text format used by Balandda resort staff, e.g.:
    29.03.2026
    1-домик
    Наличные 3.200.000
    3-домик
    Предоплата 500.000
    Перевод на карту 2.700.000
    ...
    Расходы
    Завтрак 141.898
    Инкассация Акбар 23.600.000
    ...
    Остаток 7.320.619
"""

import re
import logging
from dataclasses import dataclass, field
from datetime import date, datetime

from db.enums import (
    AccommodationType,
    ExpenseCategory,
    EXPENSE_CATEGORY_LABELS,
    PaymentMethod,
    PAYMENT_METHOD_LABELS,
)

logger = logging.getLogger(__name__)


@dataclass
class ParsedPayment:
    payment_method: PaymentMethod
    amount: float


@dataclass
class ParsedUnit:
    accommodation_type: AccommodationType
    unit_number: str | None  # "1", "5-6", etc.
    unit_label: str          # Full original text: "5-6-домик"
    service_description: str | None = None  # "Детокс 60мин"
    discount_percent: int | None = None
    discount_reason: str | None = None
    note: str | None = None  # "на 2дня"
    payments: list[ParsedPayment] = field(default_factory=list)

    @property
    def total(self) -> float:
        return sum(p.amount for p in self.payments)


@dataclass
class ParsedExpense:
    expense_category: ExpenseCategory
    description: str  # Original text
    amount: float


@dataclass
class ParsedReport:
    report_date: date
    units: list[ParsedUnit] = field(default_factory=list)
    expenses: list[ParsedExpense] = field(default_factory=list)
    reported_today_sum: float | None = None
    reported_yesterday_sum: float | None = None
    reported_total_sum: float | None = None
    reported_expense_sum: float | None = None
    reported_balance: float | None = None

    @property
    def calculated_income(self) -> float:
        return sum(u.total for u in self.units)

    @property
    def calculated_expenses(self) -> float:
        return sum(e.amount for e in self.expenses)


# ── Amount parsing ──────────────────────────────────────────────────

def parse_amount(text: str) -> float | None:
    """Parse amount like '3.200.000', '500.000', '141.898', '2*500.000'."""
    text = text.strip()

    # Handle multiplier: "2*500.000"
    mult_match = re.match(r"(\d+)\*(.+)", text)
    if mult_match:
        multiplier = int(mult_match.group(1))
        base = parse_amount(mult_match.group(2))
        if base is not None:
            return multiplier * base
        return None

    # Remove dots used as thousand separators: "3.200.000" → "3200000"
    # But keep single dot if it's a decimal: "141.898" could be 141898
    # In UZS context, all amounts are integers (no kopecks), so dots = thousands
    cleaned = text.replace(".", "").replace(",", "").replace(" ", "")
    try:
        return float(int(cleaned))
    except ValueError:
        return None


# ── Payment method detection ────────────────────────────────────────

PAYMENT_PATTERNS = [
    (r"^наличные\s+", PaymentMethod.CASH),
    (r"^предоплата\s+", PaymentMethod.PREPAYMENT),
    (r"^перевод\s+на\s+карту\s+", PaymentMethod.CARD_TRANSFER),
    (r"^перевод\s+payme?i?\s+", PaymentMethod.PAYME),
    (r"^терминал\s+viz?a\s+", PaymentMethod.TERMINAL_VISA),
    (r"^терминал\s+uzcard\s+", PaymentMethod.TERMINAL_UZCARD),
]


def try_parse_payment(line: str) -> ParsedPayment | None:
    """Try to parse a line as a payment. Returns None if not a payment line."""
    lower = line.lower().strip()

    # Skip "Предоплата DD.MM.YY" — this is a date note, not a payment
    if re.match(r"^предоплата\s+\d{1,2}\.\d{1,2}\.\d{2,4}\s*$", lower):
        return None

    for pattern, method in PAYMENT_PATTERNS:
        match = re.match(pattern, lower, re.IGNORECASE)
        if match:
            amount_str = line[match.end():].strip()
            amount = parse_amount(amount_str)
            if amount is not None:
                return ParsedPayment(payment_method=method, amount=amount)
    return None


# ── Accommodation unit detection ────────────────────────────────────

# Patterns for unit headers (order matters — more specific first)
UNIT_PATTERNS = [
    # "10-белый домик" — special white cabin
    (r"10[\s-]*бел\w*\s*домик", AccommodationType.WHITE_DOMIK, "10"),
    # "Вилла"
    (r"вилла", AccommodationType.VILLA, None),
    # "Пентхаус" / "Пинтхаус" (common misspelling)
    (r"п[еи]нтхаус", AccommodationType.PENTHOUSE, None),
    # "N-аппартамент" or "аппартамент N"
    (r"(\d[\d-]*)\s*[\s-]?\s*апп?артамент", AccommodationType.APARTMENT, None),
    (r"апп?артамент\s*(\d[\d-]*)", AccommodationType.APARTMENT, None),
    # "SPA N" or "Спа N"
    (r"(?:spa|спа)\s*(\d[\d-]*)", AccommodationType.SPA, None),
    # "Массаж"
    (r"массаж", AccommodationType.MASSAGE, None),
    # "Мини\s*бар"
    (r"мини\s*бар", AccommodationType.MINIBAR, None),
    # "Хаммам"
    (r"хаммам", AccommodationType.HAMMAM, None),
    # "N-домик" or "домик N" — general cabin (must be after белый домик)
    (r"(\d[\d-]*)\s*[\s-]?\s*домик", AccommodationType.DOMIK, None),
    (r"домик\s*(\d[\d-]*)", AccommodationType.DOMIK, None),
]


def try_parse_unit_header(line: str) -> tuple[AccommodationType, str | None, str] | None:
    """Try to parse a line as an accommodation unit header.
    Returns (type, unit_number, original_label) or None.
    """
    lower = line.lower().strip()

    for pattern, acc_type, fixed_number in UNIT_PATTERNS:
        match = re.search(pattern, lower)
        if match:
            # Extract unit number from capture group if available
            unit_number = fixed_number
            if unit_number is None and match.lastindex and match.lastindex >= 1:
                unit_number = match.group(1).strip("-")  # Remove trailing dashes
            return acc_type, unit_number, line.strip()

    return None


# ── Discount detection ──────────────────────────────────────────────

def detect_discount(line: str) -> tuple[int | None, str | None]:
    """Detect discount like '20%день рождения' or '20% день рождения'."""
    match = re.search(r"(\d+)\s*%\s*(.*)", line)
    if match:
        percent = int(match.group(1))
        reason = match.group(2).strip() or None
        return percent, reason
    return None, None


# ── Note/extra info detection ───────────────────────────────────────

def detect_note(line: str) -> str | None:
    """Detect notes like 'на 2дня', date references like 'Предоплата 30.03.26'."""
    note_patterns = [
        r"на\s+\d+\s*дн[яей]",  # "на 2дня"
        r"^предоплата\s+\d{1,2}\.\d{1,2}\.\d{2,4}",  # "Предоплата 30.03.26"
    ]
    for pattern in note_patterns:
        match = re.search(pattern, line, re.IGNORECASE)
        if match:
            return match.group(0)
    return None


# ── Expense detection ───────────────────────────────────────────────

EXPENSE_PATTERNS = [
    (r"инкассация", ExpenseCategory.INKASSATSIYA),
    (r"завтрак", ExpenseCategory.BREAKFAST),
    (r"кухн[яи]", ExpenseCategory.KITCHEN),
    (r"возврат", ExpenseCategory.REFUND),
    (r"газ\s*бал", ExpenseCategory.HOUSEHOLD),
    (r"пайнет|телефон|билайн|связь", ExpenseCategory.HOUSEHOLD),
]

# Staff name patterns — these are expense lines with staff names
STAFF_PATTERNS = [
    r"^(акбар|дилшод|илес|ильёс|ильяс)\b",
]


def try_parse_expense(line: str) -> ParsedExpense | None:
    """Try to parse a line as an expense."""
    lower = line.lower().strip()

    # Try to find amount at the end of the line
    amount_match = re.search(r"([\d.*]+(?:\.\d{3})*)\s*$", line.strip())
    if not amount_match:
        return None

    amount = parse_amount(amount_match.group(1))
    if amount is None or amount <= 0:
        return None

    description = line[:amount_match.start()].strip()
    if not description:
        return None

    # Classify the expense
    for pattern, category in EXPENSE_PATTERNS:
        if re.search(pattern, lower):
            return ParsedExpense(
                expense_category=category,
                description=description,
                amount=amount,
            )

    # Check if it's a staff payment
    for pattern in STAFF_PATTERNS:
        if re.search(pattern, lower):
            return ParsedExpense(
                expense_category=ExpenseCategory.STAFF,
                description=description,
                amount=amount,
            )

    # If we're in expense section and can't classify, mark as other
    return ParsedExpense(
        expense_category=ExpenseCategory.OTHER,
        description=description,
        amount=amount,
    )


# ── Summary line detection ──────────────────────────────────────────

SUMMARY_PATTERNS = {
    "today": r"сегодняшн\w*\s+сумма\s+([\d.]+)",
    "yesterday": r"вчерашн\w*\s+сумма\s+([\d.]+)",
    "total": r"общая\s+сумма\s+([\d.]+)",
    "expense_total": r"общая\s+сумма\s+расходов?\s+([\d.]+)",
    "balance": r"остаток\s+([\d.]+)",
}


def try_parse_summary(line: str) -> tuple[str, float] | None:
    """Try to parse a summary/total line."""
    lower = line.lower().strip()
    for key, pattern in SUMMARY_PATTERNS.items():
        match = re.search(pattern, lower)
        if match:
            amount = parse_amount(match.group(1))
            if amount is not None:
                return key, amount
    return None


# ── Main parser ─────────────────────────────────────────────────────

def parse_daily_report(text: str) -> ParsedReport | None:
    """Parse a full daily report text message into structured data."""
    lines = [l.strip() for l in text.strip().split("\n") if l.strip()]

    if not lines:
        return None

    # Parse date from first line
    date_match = re.match(r"(\d{1,2})[./](\d{1,2})[./](\d{2,4})", lines[0])
    if not date_match:
        return None

    day = int(date_match.group(1))
    month = int(date_match.group(2))
    year = int(date_match.group(3))
    if year < 100:
        year += 2000
    try:
        report_date = date(year, month, day)
    except ValueError:
        return None

    report = ParsedReport(report_date=report_date)
    current_unit: ParsedUnit | None = None
    in_expense_section = False
    service_lines: list[str] = []  # for massage service descriptions

    for line in lines[1:]:
        stripped = line.strip()
        if not stripped:
            continue

        # Check if we've entered the expense section
        if re.match(r"^расходы\s*$", stripped, re.IGNORECASE):
            # Save any pending unit
            if current_unit:
                report.units.append(current_unit)
                current_unit = None
            in_expense_section = True
            continue

        # Check for summary lines (can appear in either section)
        summary = try_parse_summary(stripped)
        if summary:
            key, amount = summary
            if key == "today":
                report.reported_today_sum = amount
            elif key == "yesterday":
                report.reported_yesterday_sum = amount
            elif key == "total" and not in_expense_section:
                report.reported_total_sum = amount
            elif key == "expense_total" or (key == "total" and in_expense_section):
                report.reported_expense_sum = amount
            elif key == "balance":
                report.reported_balance = amount
            continue

        if in_expense_section:
            expense = try_parse_expense(stripped)
            if expense:
                report.expenses.append(expense)
            continue

        # ── Income section ──

        # Check if this is a payment line
        payment = try_parse_payment(stripped)
        if payment:
            if current_unit:
                current_unit.payments.append(payment)
            continue

        # Check if this is a unit header
        unit_info = try_parse_unit_header(stripped)
        if unit_info:
            # Save previous unit
            if current_unit:
                report.units.append(current_unit)

            acc_type, unit_number, label = unit_info
            discount_pct, discount_reason = detect_discount(stripped)
            note = detect_note(stripped)

            current_unit = ParsedUnit(
                accommodation_type=acc_type,
                unit_number=unit_number,
                unit_label=label,
                discount_percent=discount_pct,
                discount_reason=discount_reason,
                note=note,
            )
            continue

        # Check for discount line (standalone, e.g. "20%день рождения")
        discount_pct, discount_reason = detect_discount(stripped)
        if discount_pct is not None and current_unit:
            current_unit.discount_percent = discount_pct
            current_unit.discount_reason = discount_reason
            continue

        # Check for standalone amount line (e.g. "2*500.000" for multiplied payments)
        if current_unit and re.match(r"^\d+\*[\d.]+$", stripped):
            amount = parse_amount(stripped)
            if amount is not None:
                # Standalone amount without method — treat as cash
                current_unit.payments.append(ParsedPayment(
                    payment_method=PaymentMethod.CASH, amount=amount
                ))
                continue

        # Check for service description (e.g. "Детокс терапия 95мин")
        if current_unit and current_unit.accommodation_type in (
            AccommodationType.MASSAGE, AccommodationType.HAMMAM, AccommodationType.SPA
        ):
            note = detect_note(stripped)
            if note:
                current_unit.note = note
            else:
                # Service description lines like "Детокс терапия 95мин"
                if current_unit.service_description:
                    current_unit.service_description += "; " + stripped
                else:
                    current_unit.service_description = stripped
            continue

        # Check for note on unit (e.g. "на 2дня")
        note = detect_note(stripped)
        if note and current_unit:
            current_unit.note = note
            continue

        # Unrecognized line — might be additional description
        if current_unit:
            if current_unit.note:
                current_unit.note += f" {stripped}"
            else:
                current_unit.note = stripped

    # Don't forget the last unit
    if current_unit:
        report.units.append(current_unit)

    return report


# ── Formatting ──────────────────────────────────────────────────────

def format_amount(amount: float) -> str:
    """Format amount as '3,200,000' for display."""
    return f"{amount:,.0f}".replace(",", ".")


def format_parsed_report(report: ParsedReport) -> str:
    """Format a parsed report as a confirmation message for the admin."""
    lines = [
        f"📊 <b>Отчёт за {report.report_date.strftime('%d.%m.%Y')}</b>",
        "",
    ]

    # Income by unit
    if report.units:
        lines.append("💰 <b>Доходы:</b>")
        for unit in report.units:
            discount = f" (скидка {unit.discount_percent}%)" if unit.discount_percent else ""
            service = f" — {unit.service_description}" if unit.service_description else ""
            lines.append(f"  <b>{unit.unit_label}</b>{discount}{service}")
            for p in unit.payments:
                method_label = PAYMENT_METHOD_LABELS.get(p.payment_method, str(p.payment_method))
                lines.append(f"    {method_label}: {format_amount(p.amount)}")
            lines.append(f"    <i>Итого: {format_amount(unit.total)}</i>")

    lines.append("")
    lines.append(f"💰 Общий доход: <b>{format_amount(report.calculated_income)}</b>")

    # Expenses
    if report.expenses:
        lines.append("")
        lines.append("💸 <b>Расходы:</b>")
        for exp in report.expenses:
            cat_label = EXPENSE_CATEGORY_LABELS.get(exp.expense_category, "Прочие")
            lines.append(f"  {exp.description}: {format_amount(exp.amount)} [{cat_label}]")
        lines.append(f"💸 Общие расходы: <b>{format_amount(report.calculated_expenses)}</b>")

    # Balance
    lines.append("")
    net = report.calculated_income - report.calculated_expenses
    lines.append(f"📈 Чистый итог: <b>{format_amount(net)}</b>")

    # Verification against reported totals
    if report.reported_today_sum is not None:
        diff = abs(report.calculated_income - report.reported_today_sum)
        status = "✅" if diff < 1000 else f"⚠️ разница {format_amount(diff)}"
        lines.append(f"\n🔍 Сверка: доход {format_amount(report.calculated_income)} vs отчёт {format_amount(report.reported_today_sum)} {status}")

    # Stats
    lines.append(f"\n📋 Юнитов: {len(report.units)} | Платежей: {sum(len(u.payments) for u in report.units)} | Расходов: {len(report.expenses)}")

    return "\n".join(lines)
