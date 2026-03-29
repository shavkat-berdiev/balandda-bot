import enum
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    DateTime,
    Enum,
    ForeignKey,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


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
