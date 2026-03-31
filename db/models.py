from datetime import datetime, date

from sqlalchemy import (
    BigInteger,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

# Import all enums and labels from the standalone module
from db.enums import (
    AccommodationType,
    ACCOMMODATION_TYPE_LABELS,
    BusinessUnit,
    ExpenseCategory,
    EXPENSE_CATEGORY_LABELS,
    Language,
    PaymentMethod,
    PAYMENT_METHOD_LABELS,
    TransactionType,
    UserRole,
)

# Re-export for backward compatibility
__all__ = [
    "Base",
    "AccommodationType", "ACCOMMODATION_TYPE_LABELS",
    "BusinessUnit",
    "ExpenseCategory", "EXPENSE_CATEGORY_LABELS",
    "Language",
    "PaymentMethod", "PAYMENT_METHOD_LABELS",
    "TransactionType",
    "UserRole",
    "User", "Category", "Transaction",
    "DailyReport", "ReportLineItem", "ReportExpense",
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
