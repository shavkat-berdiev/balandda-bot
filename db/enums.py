"""Shared enums and labels — no SQLAlchemy dependency."""

import enum


class BusinessUnit(str, enum.Enum):
    RESORT = "resort"
    RESTAURANT = "restaurant"


class TransactionType(str, enum.Enum):
    CASH_IN = "cash_in"
    CASH_OUT = "cash_out"


class UserRole(str, enum.Enum):
    ADMIN = "admin"
    RESORT_MANAGER = "resort_manager"
    RESTAURANT_MANAGER = "restaurant_manager"


class Language(str, enum.Enum):
    RU = "ru"
    UZ = "uz"


class PaymentMethod(str, enum.Enum):
    CASH = "cash"
    CARD_TRANSFER = "card_transfer"
    TERMINAL_VISA = "terminal_visa"
    TERMINAL_UZCARD = "terminal_uzcard"
    PAYME = "payme"
    PREPAYMENT = "prepayment"


class AccommodationType(str, enum.Enum):
    DOMIK = "domik"
    APARTMENT = "apartment"
    PENTHOUSE = "penthouse"
    VILLA = "villa"
    WHITE_DOMIK = "white_domik"
    SPA = "spa"
    MASSAGE = "massage"
    MINIBAR = "minibar"
    HAMMAM = "hammam"


class ExpenseCategory(str, enum.Enum):
    INKASSATSIYA = "inkassatsiya"
    BREAKFAST = "breakfast"
    KITCHEN = "kitchen"
    STAFF = "staff"
    REFUND = "refund"
    HOUSEHOLD = "household"
    OTHER = "other"


# ── Labels for display ──────────────────────────────────────────────

PAYMENT_METHOD_LABELS = {
    PaymentMethod.CASH: "Наличные",
    PaymentMethod.CARD_TRANSFER: "Перевод на карту",
    PaymentMethod.TERMINAL_VISA: "Терминал Visa",
    PaymentMethod.TERMINAL_UZCARD: "Терминал UzCard",
    PaymentMethod.PAYME: "PayMe",
    PaymentMethod.PREPAYMENT: "Предоплата",
}

ACCOMMODATION_TYPE_LABELS = {
    AccommodationType.DOMIK: "Домик",
    AccommodationType.APARTMENT: "Аппартамент",
    AccommodationType.PENTHOUSE: "Пентхаус",
    AccommodationType.VILLA: "Вилла",
    AccommodationType.WHITE_DOMIK: "10-белый домик",
    AccommodationType.SPA: "SPA",
    AccommodationType.MASSAGE: "Массаж",
    AccommodationType.MINIBAR: "Мини бар",
    AccommodationType.HAMMAM: "Хаммам",
}

EXPENSE_CATEGORY_LABELS = {
    ExpenseCategory.INKASSATSIYA: "Инкассация",
    ExpenseCategory.BREAKFAST: "Затрата на завтрак",
    ExpenseCategory.KITCHEN: "Расходы кухни",
    ExpenseCategory.STAFF: "Затрата на персонал",
    ExpenseCategory.REFUND: "Возвраты",
    ExpenseCategory.HOUSEHOLD: "Хозяйственные расходы",
    ExpenseCategory.OTHER: "Прочие расходы",
}
