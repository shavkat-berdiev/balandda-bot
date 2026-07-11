from datetime import datetime, date
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Column,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Table,
    Text,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

# Import all enums and labels from the standalone module
from db.enums import (
    AccommodationType,
    ACCOMMODATION_TYPE_LABELS,
    BusinessUnit,
    DiscountReason,
    DISCOUNT_REASON_LABELS,
    DiscountType,
    DISCOUNT_TYPE_LABELS,
    ExpenseCategory,
    EXPENSE_CATEGORY_LABELS,
    Language,
    PaymentMethod,
    PAYMENT_METHOD_LABELS,
    PrepaymentStatus,
    PREPAYMENT_STATUS_LABELS,
    PropertyType,
    PROPERTY_TYPE_LABELS,
    ReservationStatus,
    RESERVATION_STATUS_LABELS,
    ReservationSource,
    RESERVATION_SOURCE_LABELS,
    RegistrationRequestStatus,
    REGISTRATION_REQUEST_STATUS_LABELS,
    ReportStatus,
    REPORT_STATUS_LABELS,
    RestaurantIncomeCategory,
    RESTAURANT_INCOME_LABELS,
    ServiceType,
    SERVICE_TYPE_LABELS,
    TransactionType,
    UserRole,
    WalletTransactionType,
    WalletTransactionStatus,
    WALLET_TRANSACTION_TYPE_LABELS,
    PurchaseCategory,
    PURCHASE_CATEGORY_LABELS,
)

# Re-export for backward compatibility
__all__ = [
    "Base",
    "AccommodationType", "ACCOMMODATION_TYPE_LABELS",
    "BusinessUnit",
    "DiscountReason", "DISCOUNT_REASON_LABELS",
    "DiscountType", "DISCOUNT_TYPE_LABELS",
    "ExpenseCategory", "EXPENSE_CATEGORY_LABELS",
    "Language",
    "PaymentMethod", "PAYMENT_METHOD_LABELS",
    "PrepaymentStatus", "PREPAYMENT_STATUS_LABELS",
    "PropertyType", "PROPERTY_TYPE_LABELS",
    "ReportStatus", "REPORT_STATUS_LABELS",
    "Reservation", "ReservationEvent", "ReservationStatus", "RESERVATION_STATUS_LABELS",
    "ReservationSource", "RESERVATION_SOURCE_LABELS",
    "ServiceType", "SERVICE_TYPE_LABELS",
    "TransactionType",
    "UserRole",
    "User", "Category", "Transaction",
    "DailyReport", "ReportLineItem", "ReportExpense",
    "Property", "PropertyTypeLabel", "ServiceItem", "MinibarItem", "StaffMember",
    "StructuredReport", "IncomeEntry", "ExpenseEntry",
    "Prepayment",
    "WalletTransaction",
    "WalletTransactionType", "WALLET_TRANSACTION_TYPE_LABELS",
    "RegistrationRequest",
    "RegistrationRequestStatus", "REGISTRATION_REQUEST_STATUS_LABELS",
]


class Base(DeclarativeBase):
    pass


# ── Models ─────────────────────────────────────────────────────────

class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(255))
    role: Mapped[UserRole] = mapped_column(Enum(UserRole), default=UserRole.RESORT_MANAGER)
    language: Mapped[Language] = mapped_column(Enum(Language), default=Language.RU)
    active_section: Mapped[BusinessUnit] = mapped_column(
        Enum(BusinessUnit), default=BusinessUnit.RESORT
    )
    # Optional username/password login (assigned by the owner) as an alternative to
    # the Telegram Login Widget — survives Telegram's in-app browser wiping storage.
    login: Mapped[str | None] = mapped_column(String(64), unique=True, index=True, nullable=True)
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    transactions: Mapped[list["Transaction"]] = relationship(back_populates="user")


class Category(Base):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(primary_key=True)
    name_ru: Mapped[str] = mapped_column(String(100))
    name_uz: Mapped[str] = mapped_column(String(100))
    business_unit: Mapped[BusinessUnit] = mapped_column(Enum(BusinessUnit))
    transaction_type: Mapped[TransactionType] = mapped_column(Enum(TransactionType))
    is_active: Mapped[bool] = mapped_column(default=True)
    sort_order: Mapped[int] = mapped_column(default=0)

    transactions: Mapped[list["Transaction"]] = relationship(back_populates="category")


class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id"))
    business_unit: Mapped[BusinessUnit] = mapped_column(Enum(BusinessUnit))
    transaction_type: Mapped[TransactionType] = mapped_column(Enum(TransactionType))
    amount: Mapped[float] = mapped_column(Numeric(15, 2))
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped["User"] = relationship(back_populates="transactions")
    category: Mapped["Category"] = relationship(back_populates="transactions")


class DailyReport(Base):
    """Parsed daily reports forwarded by admin."""
    __tablename__ = "daily_reports"

    id: Mapped[int] = mapped_column(primary_key=True)
    report_date: Mapped[date] = mapped_column(Date, index=True)
    business_unit: Mapped[BusinessUnit] = mapped_column(Enum(BusinessUnit))
    raw_text: Mapped[str] = mapped_column(Text)
    total_income: Mapped[float] = mapped_column(Numeric(15, 2), default=0)
    total_expense: Mapped[float] = mapped_column(Numeric(15, 2), default=0)
    balance: Mapped[float] = mapped_column(Numeric(15, 2), default=0)
    previous_balance: Mapped[float] = mapped_column(Numeric(15, 2), default=0)
    imported_by: Mapped[int] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    line_items: Mapped[list["ReportLineItem"]] = relationship(back_populates="report", cascade="all, delete-orphan")
    expenses: Mapped[list["ReportExpense"]] = relationship(back_populates="report", cascade="all, delete-orphan")


class ReportLineItem(Base):
    """Individual income line from a daily report."""
    __tablename__ = "report_line_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    report_id: Mapped[int] = mapped_column(ForeignKey("daily_reports.id", ondelete="CASCADE"))
    accommodation_type: Mapped[AccommodationType] = mapped_column(Enum(AccommodationType))
    unit_number: Mapped[str | None] = mapped_column(String(20), nullable=True)
    unit_label: Mapped[str] = mapped_column(String(100))
    service_description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    payment_method: Mapped[PaymentMethod] = mapped_column(Enum(PaymentMethod))
    amount: Mapped[float] = mapped_column(Numeric(15, 2))
    discount_percent: Mapped[int | None] = mapped_column(Integer, nullable=True)
    discount_reason: Mapped[str | None] = mapped_column(String(100), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    report: Mapped["DailyReport"] = relationship(back_populates="line_items")


class ReportExpense(Base):
    """Individual expense line from a daily report."""
    __tablename__ = "report_expenses"

    id: Mapped[int] = mapped_column(primary_key=True)
    report_id: Mapped[int] = mapped_column(ForeignKey("daily_reports.id", ondelete="CASCADE"))
    expense_category: Mapped[ExpenseCategory] = mapped_column(Enum(ExpenseCategory))
    description: Mapped[str] = mapped_column(String(255))
    amount: Mapped[float] = mapped_column(Numeric(15, 2))

    report: Mapped["DailyReport"] = relationship(back_populates="expenses")


# ── New structured reporting models ────────────────────────────────

class Property(Base):
    """Resort property catalog."""
    __tablename__ = "properties"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    name_ru: Mapped[str] = mapped_column(String(100))
    name_uz: Mapped[str] = mapped_column(String(100))
    name_en: Mapped[str | None] = mapped_column(String(100), nullable=True)
    property_type: Mapped[PropertyType] = mapped_column(Enum(PropertyType))
    unit_number: Mapped[str | None] = mapped_column(String(10), nullable=True)
    capacity: Mapped[int] = mapped_column(Integer)
    has_sauna: Mapped[bool] = mapped_column(default=False)
    price_weekday: Mapped[float] = mapped_column(Numeric(15, 2))
    price_weekend: Mapped[float] = mapped_column(Numeric(15, 2))
    emoji: Mapped[str] = mapped_column(String(10), default="🏠")
    is_active: Mapped[bool] = mapped_column(default=True)
    sort_order: Mapped[int] = mapped_column(default=0)
    business_unit: Mapped[BusinessUnit] = mapped_column(Enum(BusinessUnit), default=BusinessUnit.RESORT)

    income_entries: Mapped[list["IncomeEntry"]] = relationship(back_populates="property", cascade="all, delete-orphan")


class PropertyTypeLabel(Base):
    """Editable display labels for each PropertyType, per language.

    Overrides the hard-coded PROPERTY_TYPE_LABELS so staff can rename the
    stay categories (e.g. 'Белое Шале' / 'OQ Chalet') from the admin panel.
    Consumed by the public catalog → bot + website.
    """
    __tablename__ = "property_type_labels"

    property_type: Mapped[str] = mapped_column(String(40), primary_key=True)
    label_ru: Mapped[str] = mapped_column(String(100))
    label_uz: Mapped[str] = mapped_column(String(100))
    label_en: Mapped[str | None] = mapped_column(String(100), nullable=True)


class ServiceItem(Base):
    """Massage/SPA service catalog."""
    __tablename__ = "service_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    service_type: Mapped[ServiceType] = mapped_column(Enum(ServiceType))
    name_ru: Mapped[str] = mapped_column(String(100))
    name_uz: Mapped[str] = mapped_column(String(100))
    duration_minutes: Mapped[int] = mapped_column(Integer)
    price: Mapped[float] = mapped_column(Numeric(15, 2))
    is_active: Mapped[bool] = mapped_column(default=True)
    sort_order: Mapped[int] = mapped_column(default=0)

    # --- SPA module additions (Phase 1) ---
    category_id: Mapped[int | None] = mapped_column(ForeignKey("service_categories.id", ondelete="SET NULL"), nullable=True)
    # where the procedure can be performed: 'room_only' | 'room_or_cottage' | 'cottage_only'
    location_mode: Mapped[str] = mapped_column(String(20), default="room_or_cottage")
    # master commission % of this service's price (per-service)
    master_percent: Mapped[float] = mapped_column(Numeric(5, 2), default=0)

    category: Mapped["ServiceCategory | None"] = relationship(back_populates="services")
    masters: Mapped[list["SpaMaster"]] = relationship(secondary="service_masters", back_populates="services")
    allowed_locations: Mapped[list["SpaLocation"]] = relationship(secondary="service_locations", back_populates="services")
    income_entries: Mapped[list["IncomeEntry"]] = relationship(back_populates="service_item", cascade="all, delete-orphan")


class ServiceCategory(Base):
    """Editable SPA service groups (sortable)."""
    __tablename__ = "service_categories"

    id: Mapped[int] = mapped_column(primary_key=True)
    name_ru: Mapped[str] = mapped_column(String(100))
    name_uz: Mapped[str] = mapped_column(String(100))
    is_active: Mapped[bool] = mapped_column(default=True)
    sort_order: Mapped[int] = mapped_column(default=0)

    services: Mapped[list["ServiceItem"]] = relationship(back_populates="category")


class SpaLocation(Base):
    """Editable SPA rooms/resources (hammam, massage rooms) — a limited resource."""
    __tablename__ = "spa_locations"

    id: Mapped[int] = mapped_column(primary_key=True)
    name_ru: Mapped[str] = mapped_column(String(100))
    name_uz: Mapped[str] = mapped_column(String(100))
    is_active: Mapped[bool] = mapped_column(default=True)
    sort_order: Mapped[int] = mapped_column(default=0)

    services: Mapped[list["ServiceItem"]] = relationship(secondary="service_locations", back_populates="allowed_locations")


class SpaMaster(Base):
    """SPA masters, assignable to services."""
    __tablename__ = "spa_masters"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    phone: Mapped[str | None] = mapped_column(String(30), nullable=True)
    telegram_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    is_active: Mapped[bool] = mapped_column(default=True)
    sort_order: Mapped[int] = mapped_column(default=0)

    services: Mapped[list["ServiceItem"]] = relationship(secondary="service_masters", back_populates="masters")


# M2M association tables (created explicitly in run_migrations too).
service_masters = Table(
    "service_masters",
    Base.metadata,
    Column("service_id", ForeignKey("service_items.id", ondelete="CASCADE"), primary_key=True),
    Column("master_id", ForeignKey("spa_masters.id", ondelete="CASCADE"), primary_key=True),
)

service_locations = Table(
    "service_locations",
    Base.metadata,
    Column("service_id", ForeignKey("service_items.id", ondelete="CASCADE"), primary_key=True),
    Column("location_id", ForeignKey("spa_locations.id", ondelete="CASCADE"), primary_key=True),
)


class BotTemplate(Base):
    """Unified bot content: one reply template per menu button, rendered on BOTH
    Telegram and Instagram. Single source of truth so the two channels can't drift.
    Nesting is deliberately capped at two levels (menu → submenu) to keep the
    admin screen a simple list rather than a flow-chart editor."""
    __tablename__ = "bot_templates"

    id: Mapped[int] = mapped_column(primary_key=True)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("bot_templates.id", ondelete="CASCADE"), nullable=True)
    key: Mapped[str] = mapped_column(String(40), index=True)
    # reply | submenu | book | agent
    action: Mapped[str] = mapped_column(String(16), default="reply")

    # Button labels. Instagram caps quick-reply titles at 20 chars, so it gets its own short label.
    label_ru: Mapped[str] = mapped_column(String(100), default="")
    label_uz: Mapped[str] = mapped_column(String(100), default="")
    label_en: Mapped[str] = mapped_column(String(100), default="")
    ig_label_ru: Mapped[str | None] = mapped_column(String(20), nullable=True)
    ig_label_uz: Mapped[str | None] = mapped_column(String(20), nullable=True)
    ig_label_en: Mapped[str | None] = mapped_column(String(20), nullable=True)

    body_ru: Mapped[str | None] = mapped_column(Text, nullable=True)
    body_uz: Mapped[str | None] = mapped_column(Text, nullable=True)
    body_en: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ["https://.../bot/xxx.jpg", ...] — public URLs (Meta must fetch them unauthenticated)
    images: Mapped[str | None] = mapped_column(Text, nullable=True)   # JSON array

    # none | houses | pool | spa — appends a LIVE price table from the catalog at send time
    price_block: Mapped[str] = mapped_column(String(10), default="none")

    sort_order: Mapped[int] = mapped_column(default=0)
    is_active: Mapped[bool] = mapped_column(default=True)

    children: Mapped[list["BotTemplate"]] = relationship(
        back_populates="parent", cascade="all, delete-orphan", order_by="BotTemplate.sort_order",
    )
    parent: Mapped["BotTemplate | None"] = relationship(back_populates="children", remote_side=[id])


class SpaAppointment(Base):
    """A scheduled SPA procedure: a service performed by a master, in a room, at a time."""
    __tablename__ = "spa_appointments"

    id: Mapped[int] = mapped_column(primary_key=True)
    service_id: Mapped[int] = mapped_column(ForeignKey("service_items.id"))
    master_id: Mapped[int] = mapped_column(ForeignKey("spa_masters.id"))
    location_id: Mapped[int | None] = mapped_column(ForeignKey("spa_locations.id", ondelete="SET NULL"), nullable=True)
    # optional link to a resort reservation/guest
    reservation_id: Mapped[int | None] = mapped_column(ForeignKey("reservations.id", ondelete="SET NULL"), nullable=True)
    customer_name: Mapped[str | None] = mapped_column(String(150), nullable=True)
    customer_phone: Mapped[str | None] = mapped_column(String(30), nullable=True)
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    # planned | done | cancelled | no_show
    status: Mapped[str] = mapped_column(String(16), default="planned")
    price: Mapped[float] = mapped_column(Numeric(15, 2), default=0)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    service: Mapped["ServiceItem"] = relationship(foreign_keys=[service_id])
    master: Mapped["SpaMaster"] = relationship(foreign_keys=[master_id])
    location: Mapped["SpaLocation | None"] = relationship(foreign_keys=[location_id])


class MinibarItem(Base):
    """Minibar product catalog."""
    __tablename__ = "minibar_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    name_ru: Mapped[str] = mapped_column(String(100))
    name_uz: Mapped[str] = mapped_column(String(100))
    price: Mapped[float] = mapped_column(Numeric(15, 2))
    is_active: Mapped[bool] = mapped_column(default=True)
    sort_order: Mapped[int] = mapped_column(default=0)

    income_entries: Mapped[list["IncomeEntry"]] = relationship(back_populates="minibar_item", cascade="all, delete-orphan")


class StaffMember(Base):
    """Staff members for expense attribution."""
    __tablename__ = "staff_members"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    role_description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(default=True)

    expense_entries: Mapped[list["ExpenseEntry"]] = relationship(back_populates="staff_member", cascade="all, delete-orphan")


class StructuredReport(Base):
    """New structured daily report (replaces text-based DailyReport for new flow)."""
    __tablename__ = "structured_reports"

    id: Mapped[int] = mapped_column(primary_key=True)
    report_date: Mapped[date] = mapped_column(Date, index=True)
    business_unit: Mapped[BusinessUnit] = mapped_column(Enum(BusinessUnit))
    status: Mapped[ReportStatus] = mapped_column(Enum(ReportStatus), default=ReportStatus.DRAFT)
    submitted_by: Mapped[int] = mapped_column(BigInteger)
    total_income: Mapped[float] = mapped_column(Numeric(15, 2), default=0)
    total_expense: Mapped[float] = mapped_column(Numeric(15, 2), default=0)
    previous_balance: Mapped[float] = mapped_column(Numeric(15, 2), default=0)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    income_entries: Mapped[list["IncomeEntry"]] = relationship(back_populates="report", cascade="all, delete-orphan")
    expense_entries: Mapped[list["ExpenseEntry"]] = relationship(back_populates="report", cascade="all, delete-orphan")


class IncomeEntry(Base):
    """Individual income line in structured report."""
    __tablename__ = "income_entries"

    id: Mapped[int] = mapped_column(primary_key=True)
    report_id: Mapped[int] = mapped_column(ForeignKey("structured_reports.id", ondelete="CASCADE"))
    property_id: Mapped[int | None] = mapped_column(ForeignKey("properties.id"), nullable=True)
    service_item_id: Mapped[int | None] = mapped_column(ForeignKey("service_items.id"), nullable=True)
    minibar_item_id: Mapped[int | None] = mapped_column(ForeignKey("minibar_items.id"), nullable=True)
    reservation_id: Mapped[int | None] = mapped_column(ForeignKey("reservations.id"), nullable=True, index=True)
    restaurant_category: Mapped[RestaurantIncomeCategory | None] = mapped_column(Enum(RestaurantIncomeCategory), nullable=True)
    payment_method: Mapped[PaymentMethod] = mapped_column(Enum(PaymentMethod))
    amount: Mapped[float] = mapped_column(Numeric(15, 2))
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    num_days: Mapped[int] = mapped_column(Integer, default=1)
    discount_type: Mapped[DiscountType | None] = mapped_column(Enum(DiscountType), nullable=True)
    discount_value: Mapped[float | None] = mapped_column(Numeric(15, 2), nullable=True)
    discount_reason: Mapped[DiscountReason | None] = mapped_column(Enum(DiscountReason), nullable=True)
    discount_note: Mapped[str | None] = mapped_column(String(255), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    report: Mapped["StructuredReport"] = relationship(back_populates="income_entries")
    property: Mapped["Property | None"] = relationship(back_populates="income_entries")
    service_item: Mapped["ServiceItem | None"] = relationship(back_populates="income_entries")
    minibar_item: Mapped["MinibarItem | None"] = relationship(back_populates="income_entries")


class ExpenseEntry(Base):
    """Individual expense in structured report."""
    __tablename__ = "expense_entries"

    id: Mapped[int] = mapped_column(primary_key=True)
    report_id: Mapped[int] = mapped_column(ForeignKey("structured_reports.id", ondelete="CASCADE"))
    expense_category: Mapped[ExpenseCategory] = mapped_column(Enum(ExpenseCategory))
    staff_member_id: Mapped[int | None] = mapped_column(ForeignKey("staff_members.id"), nullable=True)
    amount: Mapped[float] = mapped_column(Numeric(15, 2))
    description: Mapped[str] = mapped_column(String(255))
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    report: Mapped["StructuredReport"] = relationship(back_populates="expense_entries")
    staff_member: Mapped["StaffMember | None"] = relationship(back_populates="expense_entries")


class Prepayment(Base):
    """Prepayment records — separate cashflow tracked by operators."""
    __tablename__ = "prepayments"

    id: Mapped[int] = mapped_column(primary_key=True)
    guest_name: Mapped[str] = mapped_column(String(255))
    property_id: Mapped[int] = mapped_column(ForeignKey("properties.id"))
    check_in_date: Mapped[date] = mapped_column(Date, index=True)
    check_out_date: Mapped[date] = mapped_column(Date)
    amount: Mapped[float] = mapped_column(Numeric(15, 2))
    payment_method: Mapped[str] = mapped_column(String(50), default="CARD_TRANSFER")
    status: Mapped[PrepaymentStatus] = mapped_column(
        Enum(PrepaymentStatus), default=PrepaymentStatus.PENDING
    )
    screenshot_file_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    screenshot_url: Mapped[str | None] = mapped_column(String(255), nullable=True)  # web-uploaded proof (disk path)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    operator_telegram_id: Mapped[int] = mapped_column(BigInteger, index=True)
    settled_in_report_id: Mapped[int | None] = mapped_column(
        ForeignKey("structured_reports.id"), nullable=True
    )
    # Links when a prepayment is created/mirrored from the bookings calendar.
    # One reservation can have many (partial) prepayments; each mirrors one income line.
    reservation_id: Mapped[int | None] = mapped_column(
        ForeignKey("reservations.id", ondelete="SET NULL"), nullable=True, index=True
    )
    income_entry_id: Mapped[int | None] = mapped_column(
        ForeignKey("income_entries.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    property: Mapped["Property"] = relationship()
    settled_in_report: Mapped["StructuredReport | None"] = relationship()


class WalletTransaction(Base):
    """Cash wallet transactions — tracks cash flow between users."""
    __tablename__ = "wallet_transactions"

    id: Mapped[int] = mapped_column(primary_key=True)
    sender_telegram_id: Mapped[int] = mapped_column(BigInteger, index=True)
    receiver_telegram_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(15, 2))
    transaction_type: Mapped[WalletTransactionType] = mapped_column(Enum(WalletTransactionType))
    status: Mapped[WalletTransactionStatus] = mapped_column(
        Enum(WalletTransactionStatus), default=WalletTransactionStatus.COMPLETED,
        server_default="COMPLETED",
    )
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    report_id: Mapped[int | None] = mapped_column(ForeignKey("structured_reports.id"), nullable=True)
    business_unit: Mapped[BusinessUnit | None] = mapped_column(Enum(BusinessUnit), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PurchaseReport(Base):
    """Purchase report — groups multiple purchase entries into a daily report."""
    __tablename__ = "purchase_reports"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_telegram_id: Mapped[int] = mapped_column(BigInteger, index=True)
    report_date: Mapped[date] = mapped_column(Date)
    business_unit: Mapped[BusinessUnit] = mapped_column(Enum(BusinessUnit))
    status: Mapped[ReportStatus] = mapped_column(
        Enum(ReportStatus), default=ReportStatus.DRAFT
    )
    total_amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    entries: Mapped[list["PurchaseEntry"]] = relationship(
        back_populates="report", cascade="all, delete-orphan"
    )


class PurchaseEntry(Base):
    """Individual purchase entry within a purchase report."""
    __tablename__ = "purchase_entries"

    id: Mapped[int] = mapped_column(primary_key=True)
    report_id: Mapped[int] = mapped_column(ForeignKey("purchase_reports.id"), index=True)
    category: Mapped[PurchaseCategory] = mapped_column(Enum(PurchaseCategory))
    amount: Mapped[Decimal] = mapped_column(Numeric(15, 2))
    description: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    report: Mapped["PurchaseReport"] = relationship(back_populates="entries")


class RegistrationRequest(Base):
    """Registration requests from unregistered Telegram users."""
    __tablename__ = "registration_requests"

    id: Mapped[int] = mapped_column(primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, index=True)
    full_name: Mapped[str] = mapped_column(String(255))
    username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[RegistrationRequestStatus] = mapped_column(
        Enum(RegistrationRequestStatus), default=RegistrationRequestStatus.PENDING
    )
    reviewed_by: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    assigned_role: Mapped[UserRole | None] = mapped_column(Enum(UserRole), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Reservation(Base):
    """A booking (or manual block) on a specific unit (Property). Powers the
    availability calendar. Overlap on the same unit is prevented by a Postgres
    GiST exclusion constraint added in run_migrations()."""
    __tablename__ = "reservations"

    id: Mapped[int] = mapped_column(primary_key=True)
    property_id: Mapped[int] = mapped_column(ForeignKey("properties.id"), index=True)
    guest_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    guest_phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    guest_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Telegram link to the customer chat — @nickname now (agent-entered or self-service),
    # numeric user id filled once the customer has interacted with the bot (needed to DM them).
    telegram_username: Mapped[str | None] = mapped_column(String(100), nullable=True)
    telegram_user_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    check_in: Mapped[date] = mapped_column(Date, index=True)
    check_out: Mapped[date] = mapped_column(Date)
    status: Mapped[ReservationStatus] = mapped_column(
        Enum(ReservationStatus), default=ReservationStatus.HOLD, index=True
    )
    source: Mapped[ReservationSource] = mapped_column(
        Enum(ReservationSource), default=ReservationSource.DIRECT
    )
    total_amount: Mapped[float | None] = mapped_column(Numeric(15, 2), nullable=True)
    deposit_amount: Mapped[float | None] = mapped_column(Numeric(15, 2), nullable=True)
    prepayment_id: Mapped[int | None] = mapped_column(ForeignKey("prepayments.id"), nullable=True)
    # Unpaid-hold lifecycle (working-hours aware, set at creation, cleared on first payment)
    hold_warn_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    hold_warned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    hold_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Customer Telegram messaging (connect deep-link + one-time send guards)
    connect_token: Mapped[str | None] = mapped_column(String(32), unique=True, index=True, nullable=True)
    booking_notified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    confirmed_notified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Channel-manager (Beds24) booking id — dedupes OTA imports (Booking.com/Airbnb/Trip.com)
    channel_booking_id: Mapped[str | None] = mapped_column(String(64), unique=True, index=True, nullable=True)
    created_by: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    property: Mapped["Property"] = relationship()


class ReservationEvent(Base):
    """Audit log for a reservation: who changed what and when."""
    __tablename__ = "reservation_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    reservation_id: Mapped[int | None] = mapped_column(
        ForeignKey("reservations.id", ondelete="SET NULL"), index=True, nullable=True
    )
    actor_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    actor_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    action: Mapped[str] = mapped_column(String(40))  # created / updated / cancelled / auto
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
