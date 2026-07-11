"""Shared enums and labels — no SQLAlchemy dependency."""

import enum


class BusinessUnit(str, enum.Enum):
    RESORT = "RESORT"
    RESTAURANT = "RESTAURANT"


class TransactionType(str, enum.Enum):
    CASH_IN = "CASH_IN"
    CASH_OUT = "CASH_OUT"


class UserRole(str, enum.Enum):
    OWNER = "OWNER"
    ADMIN = "ADMIN"
    RESORT_MANAGER = "RESORT_MANAGER"
    RESTAURANT_MANAGER = "RESTAURANT_MANAGER"
    OPERATOR = "OPERATOR"
    PURCHASER = "PURCHASER"


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
    POOL_LARGE_CABIN = "POOL_LARGE_CABIN"   # бассейн — большой шатёр
    POOL_SMALL_CABIN = "POOL_SMALL_CABIN"   # бассейн — белый шатёр
    POOL_TABLE = "POOL_TABLE"               # бассейн — стол


class ReservationStatus(str, enum.Enum):
    HOLD = "HOLD"            # tentative — awaiting prepayment (shown red)
    CONFIRMED = "CONFIRMED"
    CHECKED_IN = "CHECKED_IN"
    CHECKED_OUT = "CHECKED_OUT"
    CANCELLED = "CANCELLED"
    NO_SHOW = "NO_SHOW"
    BLOCKED = "BLOCKED"      # manual block (maintenance / owner hold)
    EXPIRED = "EXPIRED"      # hold lapsed unpaid (shown pale grey, date freed)


class ReservationSource(str, enum.Enum):
    DIRECT = "DIRECT"        # website self-service booking
    PHONE = "PHONE"
    TELEGRAM = "TELEGRAM"
    INSTAGRAM = "INSTAGRAM"
    BOOKING_COM = "BOOKING_COM"
    AIRBNB = "AIRBNB"
    TRIP_COM = "TRIP_COM"   # via Beds24 channel manager
    MANUAL = "MANUAL"        # entered by staff / manual block


RESERVATION_STATUS_LABELS = {
    ReservationStatus.HOLD: "Бронь (ожидает оплаты)",
    ReservationStatus.CONFIRMED: "Подтверждено",
    ReservationStatus.CHECKED_IN: "Заселён",
    ReservationStatus.CHECKED_OUT: "Выселен",
    ReservationStatus.CANCELLED: "Отменено",
    ReservationStatus.NO_SHOW: "Не приехал",
    ReservationStatus.BLOCKED: "Заблокировано",
    ReservationStatus.EXPIRED: "Истекло (не оплачено)",
}

RESERVATION_SOURCE_LABELS = {
    ReservationSource.DIRECT: "Сайт",
    ReservationSource.PHONE: "Телефон",
    ReservationSource.TELEGRAM: "Telegram",
    ReservationSource.INSTAGRAM: "Instagram",
    ReservationSource.BOOKING_COM: "Booking.com",
    ReservationSource.AIRBNB: "Airbnb",
    ReservationSource.TRIP_COM: "Trip.com",
    ReservationSource.MANUAL: "Вручную",
}


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


class PurchaseCategory(str, enum.Enum):
    # Restaurant categories
    VEGETABLES_FRUITS = "VEGETABLES_FRUITS"
    MEAT_PRODUCTS = "MEAT_PRODUCTS"
    DAIRY_CHEESE = "DAIRY_CHEESE"
    CONSTRUCTION_MATERIALS = "CONSTRUCTION_MATERIALS"
    HOUSEHOLD_SUPPLIES_REST = "HOUSEHOLD_SUPPLIES_REST"
    POOL_SUPPLIES_REST = "POOL_SUPPLIES_REST"
    OTHER_RESTAURANT = "OTHER_RESTAURANT"
    # Resort categories
    CLEANING_SUPPLIES = "CLEANING_SUPPLIES"
    HOUSEHOLD_SUPPLIES = "HOUSEHOLD_SUPPLIES"
    POOL_SUPPLIES = "POOL_SUPPLIES"
    EQUIPMENT = "EQUIPMENT"
    SAUNA_PARTS = "SAUNA_PARTS"
    TABLEWARE = "TABLEWARE"
    OTHER_RESORT = "OTHER_RESORT"


class WalletTransactionType(str, enum.Enum):
    CASH_IN = "CASH_IN"                  # Auto from cash income report
    TRANSFER_TO_EMPLOYEE = "TRANSFER_TO_EMPLOYEE"  # Between staff
    TRANSFER_TO_SHAVKAT = "TRANSFER_TO_SHAVKAT"    # Final dest: owner
    CASH_TO_BANK = "CASH_TO_BANK"        # Final dest: bank
    PURCHASE = "PURCHASE"                # Deduction for purchase
    ADJUSTMENT = "ADJUSTMENT"            # Owner correction (signed delta)


class WalletTransactionStatus(str, enum.Enum):
    PENDING = "PENDING"        # Awaiting receiver acceptance
    COMPLETED = "COMPLETED"    # Accepted / auto-completed
    CANCELLED = "CANCELLED"    # Declined by receiver


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
    PropertyType.POOL_LARGE_CABIN: "Терасса (бассейн)",
    PropertyType.POOL_SMALL_CABIN: "Кабинка (бассейн)",
    PropertyType.POOL_TABLE: "Шатёр (бассейн)",
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

PURCHASE_CATEGORY_LABELS = {
    PurchaseCategory.VEGETABLES_FRUITS: "Овощи и фрукты",
    PurchaseCategory.MEAT_PRODUCTS: "Мясные изделия",
    PurchaseCategory.DAIRY_CHEESE: "Молочка и сыры",
    PurchaseCategory.CONSTRUCTION_MATERIALS: "Строй материалы",
    PurchaseCategory.HOUSEHOLD_SUPPLIES_REST: "Хоз материалы",
    PurchaseCategory.POOL_SUPPLIES_REST: "Средства бассейна",
    PurchaseCategory.OTHER_RESTAURANT: "Прочее",
    PurchaseCategory.CLEANING_SUPPLIES: "Моющие средства",
    PurchaseCategory.HOUSEHOLD_SUPPLIES: "Хоз материалы",
    PurchaseCategory.POOL_SUPPLIES: "Средства бассейна",
    PurchaseCategory.EQUIPMENT: "Техника",
    PurchaseCategory.SAUNA_PARTS: "Запчасти Сауны",
    PurchaseCategory.TABLEWARE: "Посуда",
    PurchaseCategory.OTHER_RESORT: "Прочее",
}

PURCHASE_CATEGORIES_RESTAURANT = [
    PurchaseCategory.VEGETABLES_FRUITS,
    PurchaseCategory.MEAT_PRODUCTS,
    PurchaseCategory.DAIRY_CHEESE,
    PurchaseCategory.CONSTRUCTION_MATERIALS,
    PurchaseCategory.HOUSEHOLD_SUPPLIES_REST,
    PurchaseCategory.POOL_SUPPLIES_REST,
    PurchaseCategory.OTHER_RESTAURANT,
]

PURCHASE_CATEGORIES_RESORT = [
    PurchaseCategory.CLEANING_SUPPLIES,
    PurchaseCategory.HOUSEHOLD_SUPPLIES,
    PurchaseCategory.POOL_SUPPLIES,
    PurchaseCategory.EQUIPMENT,
    PurchaseCategory.SAUNA_PARTS,
    PurchaseCategory.TABLEWARE,
    PurchaseCategory.OTHER_RESORT,
]

WALLET_TRANSACTION_TYPE_LABELS = {
    WalletTransactionType.CASH_IN: "Приход наличных",
    WalletTransactionType.TRANSFER_TO_EMPLOYEE: "Передача сотруднику",
    WalletTransactionType.TRANSFER_TO_SHAVKAT: "Передано Шавкату",
    WalletTransactionType.CASH_TO_BANK: "Сдано в банк",
    WalletTransactionType.PURCHASE: "Закуп",
    WalletTransactionType.ADJUSTMENT: "Корректировка",
}
