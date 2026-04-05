"""Shared enums and labels — no SQLAlchemy dependency."""

import enum


class BusinessUnit(str, enum.Enum):
    RESORT = "RESORT"
    RESTAURANT = "RESTAURANT"


class TransactionType(str, enum.Enum):
    CASH_IN = "CASH_IN"
    CASH_OUT = "CASH_OUT"


class UserRole(str, enum.Enum):
    ADMIN = "ADMIN"
    RESORT_MANAGER = "RESORT_MANAGER"
    RESTAURANT_MANAGER = "RESTAURANT_MANAGER"
    OPERATOR = "OPERATOR"


class Language(str, enum.Enum):
    RU = "RU"
    UZ = "UZ"


class PaymentMethod(str, enum.Enum):
    CASH = "CASH"
    CARD_TRANSFER = "CARD_TRANSFER"
    TERMINAL_VISA = "TERMINAL_VISA"
    TERMINAL_UZCARD = "TERMINAL_UZCARD"
    PAYME = "PAYME"
    PREPAYMENT = "PREPAYMENT"


class AccommodationType(str, enum.Enum):
    DOMIK = "DOMIK"
    APARTMENT = "APARTMENT"
    PENTHOUSE = "PENTHOUSE"
    VILLA = "VILLA"
    WHITE_DOMIK = "WHITE_DOMIK"
    SPA = "SPA"
    MASSAGE = "MASSAGE"
    MINIBAR = "MINIBAR"
    HAMMAM = "HAMMAM"


class ExpenseCategory(str, enum.Enum):
    INKASSATSIYA = "INKASSATSIYA"
    BREAKFAST = "BREAKFAST"
    KITCHEN = "KITCHEN"
    STAFF = "STAFF"
    SALARY = "SALARY"
    REFUND = "REFUND"
    HOUSEHOLD = "HOUSEHOLD"
    REPAIR = "REPAIR"
    DELIVERY = "DELIVERY"
    OTHER = "OTHER"


class DiscountType(str, enum.Enum):
    PERCENTAGE = "PERCENTAGE"
    FIXED_AMOUNT = "FIXED_AMOUNT"


class DiscountReason(str, enum.Enum):
    BIRTHDAY = "BIRTHDAY"
    VIP_GUEST = "VIP_GUEST"
    PROMOTION = "PROMOTION"
    STAFF_REFERRAL = "STAFF_REFERRAL"
    OTHER = "OTHER"


class RestaurantIncomeCategory(str, enum.Enum):
    FOOD = "FOOD"
    DRINKS = "DRINKS"
    BANQUET = "BANQUET"
    DELIVERY = "DELIVERY"
    OTHER = "OTHER"


class ServiceType(str, enum.Enum):
    CLASSIC_AROMA_45 = "CLASSIC_AROMA_45"
    CLASSIC_AROMA_60 = "CLASSIC_AROMA_60"
    DETOX_60 = "DETOX_60"
    DETOX_95 = "DETOX_95"
    FOOT_MASSAGE_30 = "FOOT_MASSAGE_30"
    BACK_MASSAGE_30 = "BACK_MASSAGE_30"
    HAMMAM = "HAMMAM"
    OTHER_SERVICE = "OTHER_SERVICE"


class PropertyType(str, enum.Enum):
    CHALET_WITH_SAUNA = "CHALET_WITH_SAUNA"
    CHALET_WITHOUT_SAUNA = "CHALET_WITHOUT_SAUNA"
    WHITE_CHALET = "WHITE_CHALET"
    APARTMENT = "APARTMENT"
    PENTHOUSE = "PENTHOUSE"
    VILLA = "VILLA"
    SPA_SUITE = "SPA_SUITE"


class ReportStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    SUBMITTED = "SUBMITTED"
    APPROVED = "APPROVED"


class PrepaymentStatus(str, enum.Enum):
    PENDING = "PENDING"
    CONFIRMED = "CONFIRMED"
    SETTLED = "SETTLED"
    CANCELLED = "CANCELLED"


class RegistrationRequestStatus(str, enum.Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class WalletTransactionType(str, enum.Enum):
    CASH_IN = "CASH_IN"                  # Auto from cash income report
    TRANSFER_TO_EMPLOYEE = "TRANSFER_TO_EMPLOYEE"  # Between staff
    TRANSFER_TO_SHAVKAT = "TRANSFER_TO_SHAVKAT"    # Final dest: owner
    CASH_TO_BANK = "CASH_TO_BANK"        # Final dest: bank


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
    ExpenseCategory.SALARY: "Зарплата",
    ExpenseCategory.REFUND: "Возвраты",
    ExpenseCategory.HOUSEHOLD: "Хозяйственные расходы",
    ExpenseCategory.REPAIR: "Ремонт",
    ExpenseCategory.DELIVERY: "Доставка",
    ExpenseCategory.OTHER: "Прочие расходы",
}

DISCOUNT_TYPE_LABELS = {
    DiscountType.PERCENTAGE: "Процент",
    DiscountType.FIXED_AMOUNT: "Фиксированная сумма",
}

DISCOUNT_REASON_LABELS = {
    DiscountReason.BIRTHDAY: "День рождения",
    DiscountReason.VIP_GUEST: "VIP гость",
    DiscountReason.PROMOTION: "Акция",
    DiscountReason.STAFF_REFERRAL: "Рекомендация персонала",
    DiscountReason.OTHER: "Другое",
}

RESTAURANT_INCOME_LABELS = {
    RestaurantIncomeCategory.FOOD: "Еда",
    RestaurantIncomeCategory.DRINKS: "Напитки",
    RestaurantIncomeCategory.BANQUET: "Банкет",
    RestaurantIncomeCategory.DELIVERY: "Доставка",
    RestaurantIncomeCategory.OTHER: "Другое",
}

SERVICE_TYPE_LABELS = {
    ServiceType.CLASSIC_AROMA_45: "Классический аромамассаж 45мин",
    ServiceType.CLASSIC_AROMA_60: "Классический аромамассаж 60мин",
    ServiceType.DETOX_60: "Детокс терапия 60мин",
    ServiceType.DETOX_95: "Детокс терапия 95мин",
    ServiceType.FOOT_MASSAGE_30: "Массаж для ног 30мин",
    ServiceType.BACK_MASSAGE_30: "Массаж спины 30мин",
    ServiceType.HAMMAM: "Хаммам",
    ServiceType.OTHER_SERVICE: "Другое",
}

PROPERTY_TYPE_LABELS = {
    PropertyType.CHALET_WITH_SAUNA: "Домик с сауной",
    PropertyType.CHALET_WITHOUT_SAUNA: "Домик без сауны",
    PropertyType.WHITE_CHALET: "10-Белое Шале",
    PropertyType.APARTMENT: "Апартамент",
    PropertyType.PENTHOUSE: "Пентхаус",
    PropertyType.VILLA: "Вилла",
    PropertyType.SPA_SUITE: "SPA Сьют",
}

REPORT_STATUS_LABELS = {
    ReportStatus.DRAFT: "Черновик",
    ReportStatus.SUBMITTED: "Отправлено",
    ReportStatus.APPROVED: "Одобрено",
}

PREPAYMENT_STATUS_LABELS = {
    PrepaymentStatus.PENDING: "Ожидает",
    PrepaymentStatus.CONFIRMED: "Подтверждён",
    PrepaymentStatus.SETTLED: "Зачтён",
    PrepaymentStatus.CANCELLED: "Отменён",
}

REGISTRATION_REQUEST_STATUS_LABELS = {
    RegistrationRequestStatus.PENDING: "Ожидает",
    RegistrationRequestStatus.APPROVED: "Одобрено",
    RegistrationRequestStatus.REJECTED: "Отклонено",
}

WALLET_TRANSACTION_TYPE_LABELS = {
    WalletTransactionType.CASH_IN: "Приход наличных",
    WalletTransactionType.TRANSFER_TO_EMPLOYEE: "Передача сотруднику",
    WalletTransactionType.TRANSFER_TO_SHAVKAT: "Передано Шавкату",
    WalletTransactionType.CASH_TO_BANK: "Сдано в банк",
}
