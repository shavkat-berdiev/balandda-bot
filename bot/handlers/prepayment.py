"""Prepayment handler — quick flow for recording advance payments.

Flow:
1. User taps "Предоплата" on main menu
2. Date picker (today + future dates, up to 90 days forward)
3. Select property
4. Enter amount
5. Confirm → saves as IncomeEntry with payment_method=PREPAYMENT
"""

import logging
from datetime import date, timedelta
from decimal import Decimal

from aiogram import F, Router, types
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import select

from bot.keyboards.main import main_menu_keyboard
from bot.locales import get_text
from db.database import async_session
from db.enums import PaymentMethod
from db.models import (
    IncomeEntry,
    Property,
    StructuredReport,
    User,
    ReportStatus,
    BusinessUnit,
)

router = Router()
logger = logging.getLogger(__name__)

MAX_FUTURE_DAYS = 90
DAY_NAMES_RU = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
MONTH_NAMES_RU = [
    "", "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
    "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь",
]


class PrepaymentStates(StatesGroup):
    choosing_date = State()
    choosing_property = State()
    entering_amount = State()
    confirming = State()


def format_amount(amount) -> str:
    if isinstance(amount, str):
        amount = float(amount)
    elif isinstance(amount, Decimal):
        amount = float(amount)
    return f"{amount:,.0f}".replace(",", ".")


async def get_user(telegram_id: int) -> User | None:
    async with async_session() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == telegram_id)
        )
        return result.scalar_one_or_none()


def _build_future_date_picker(year: int, month: int) -> InlineKeyboardMarkup:
    """Build a calendar showing today + future dates only."""
    import calendar

    today = date.today()
    max_date = today + timedelta(days=MAX_FUTURE_DAYS)

    buttons = []

    # Month/year header with nav arrows
    buttons.append([
        InlineKeyboardButton(text="◀️", callback_data=f"pcal:prev:{year}:{month}"),
        InlineKeyboardButton(text=f"{MONTH_NAMES_RU[month]} {year}", callback_data="pcal:noop"),
        InlineKeyboardButton(text="▶️", callback_data=f"pcal:next:{year}:{month}"),
    ])

    # Day-of-week header
    buttons.append([
        InlineKeyboardButton(text=d, callback_data="pcal:noop") for d in DAY_NAMES_RU
    ])

    # Day grid
    cal = calendar.monthcalendar(year, month)
    for week in cal:
        row = []
        for day_num in week:
            if day_num == 0:
                row.append(InlineKeyboardButton(text=" ", callback_data="pcal:noop"))
            else:
                d = date(year, month, day_num)
                if d < today or d > max_date:
                    row.append(InlineKeyboardButton(text="·", callback_data="pcal:noop"))
                elif d == today:
                    row.append(InlineKeyboardButton(
                        text=f"[{day_num}]",
                        callback_data=f"pcal:day:{d.isoformat()}",
                    ))
                else:
                    row.append(InlineKeyboardButton(
                        text=str(day_num),
                        callback_data=f"pcal:day:{d.isoformat()}",
                    ))
        buttons.append(row)

    buttons.append([InlineKeyboardButton(text="❌ Отмена", callback_data="prepay:cancel")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


# ── Entry point ───────────────────────────────────────────────────


@router.callback_query(F.data == "action:prepayment")
async def on_prepayment_start(callback: types.CallbackQuery, state: FSMContext):
    """Start prepayment flow — show date picker (today + future)."""
    user = await get_user(callback.from_user.id)
    if not user:
        await callback.answer("Пользователь не найден")
        return

    lang = user.language.value.lower()
    await state.update_data(
        lang=lang,
        user_id=user.id,
        business_unit=user.active_section.value,
    )

    today = date.today()
    tomorrow = today + timedelta(days=1)

    buttons = [
        [InlineKeyboardButton(
            text=f"📅 Сегодня ({today.strftime('%d.%m')})",
            callback_data=f"pcal:day:{today.isoformat()}",
        )],
        [InlineKeyboardButton(
            text=f"📅 Завтра ({tomorrow.strftime('%d.%m')})",
            callback_data=f"pcal:day:{tomorrow.isoformat()}",
        )],
        [InlineKeyboardButton(
            text="📆 Выбрать дату...",
            callback_data=f"pcal:show:{today.year}:{today.month}",
        )],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="prepay:cancel")],
    ]

    await state.set_state(PrepaymentStates.choosing_date)
    await callback.message.edit_text(
        "💵 Предоплата\n\nВыберите дату заезда:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
    )
    await callback.answer()


# ── Calendar navigation ───────────────────────────────────────────


@router.callback_query(F.data.startswith("pcal:show:"), PrepaymentStates.choosing_date)
async def on_prepay_show_cal(callback: types.CallbackQuery, state: FSMContext):
    parts = callback.data.split(":")
    year, month = int(parts[2]), int(parts[3])
    keyboard = _build_future_date_picker(year, month)
    await callback.message.edit_text("📆 Выберите дату заезда:", reply_markup=keyboard)
    await callback.answer()


@router.callback_query(F.data.startswith("pcal:prev:"), PrepaymentStates.choosing_date)
async def on_prepay_cal_prev(callback: types.CallbackQuery, state: FSMContext):
    parts = callback.data.split(":")
    year, month = int(parts[2]), int(parts[3])
    month -= 1
    if month < 1:
        month = 12
        year -= 1
    keyboard = _build_future_date_picker(year, month)
    await callback.message.edit_text("📆 Выберите дату заезда:", reply_markup=keyboard)
    await callback.answer()


@router.callback_query(F.data.startswith("pcal:next:"), PrepaymentStates.choosing_date)
async def on_prepay_cal_next(callback: types.CallbackQuery, state: FSMContext):
    parts = callback.data.split(":")
    year, month = int(parts[2]), int(parts[3])
    month += 1
    if month > 12:
        month = 1
        year += 1
    keyboard = _build_future_date_picker(year, month)
    await callback.message.edit_text("📆 Выберите дату заезда:", reply_markup=keyboard)
    await callback.answer()


@router.callback_query(F.data == "pcal:noop", PrepaymentStates.choosing_date)
async def on_prepay_noop(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()


# ── Date selected → property picker ───────────────────────────────


@router.callback_query(F.data.startswith("pcal:day:"), PrepaymentStates.choosing_date)
async def on_prepay_date_selected(callback: types.CallbackQuery, state: FSMContext):
    """Date selected — show property list."""
    date_str = callback.data.split(":", 2)[2]
    selected_date = date.fromisoformat(date_str)

    await state.update_data(prepay_date=date_str)

    # Load active properties
    async with async_session() as session:
        result = await session.execute(
            select(Property)
            .where(Property.is_active == True)
            .order_by(Property.sort_order)
        )
        properties = result.scalars().all()

    buttons = []
    for prop in properties:
        emoji = prop.emoji or "🏠"
        label = f"{emoji} {prop.name_ru}"
        buttons.append(InlineKeyboardButton(text=label, callback_data=f"pprop:{prop.id}"))

    # 2-column layout
    keyboard_buttons = []
    for i in range(0, len(buttons), 2):
        row = [buttons[i]]
        if i + 1 < len(buttons):
            row.append(buttons[i + 1])
        keyboard_buttons.append(row)

    keyboard_buttons.append([
        InlineKeyboardButton(text="❌ Отмена", callback_data="prepay:cancel")
    ])

    await state.set_state(PrepaymentStates.choosing_property)
    await callback.message.edit_text(
        f"💵 Предоплата на {selected_date.strftime('%d.%m.%Y')}\n\n"
        f"🏠 Выберите объект:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard_buttons),
    )
    await callback.answer()


# ── Property selected → enter amount ──────────────────────────────


@router.callback_query(F.data.startswith("pprop:"), PrepaymentStates.choosing_property)
async def on_prepay_property_selected(callback: types.CallbackQuery, state: FSMContext):
    """Property selected — ask for amount."""
    prop_id = int(callback.data.split(":")[1])
    data = await state.get_data()

    async with async_session() as session:
        result = await session.execute(select(Property).where(Property.id == prop_id))
        prop = result.scalar_one_or_none()

    if not prop:
        await callback.answer("Объект не найден")
        return

    await state.update_data(prepay_property_id=prop_id, prepay_property_name=prop.name_ru)
    await state.set_state(PrepaymentStates.entering_amount)

    prepay_date = date.fromisoformat(data["prepay_date"])
    await callback.message.edit_text(
        f"💵 Предоплата\n"
        f"📅 {prepay_date.strftime('%d.%m.%Y')}\n"
        f"🏠 {prop.name_ru}\n\n"
        f"Введите сумму предоплаты:"
    )
    await callback.answer()


# ── Amount entered → confirmation ─────────────────────────────────


@router.message(PrepaymentStates.entering_amount)
async def on_prepay_amount_entered(message: types.Message, state: FSMContext):
    """Amount entered — show confirmation."""
    raw = message.text.strip().replace(" ", "").replace(",", "").replace(".", "")
    try:
        amount = Decimal(raw)
        if amount <= 0:
            raise ValueError
    except (ValueError, Exception):
        await message.answer("❌ Введите корректную сумму (только цифры)")
        return

    data = await state.get_data()
    await state.update_data(prepay_amount=str(amount))

    prepay_date = date.fromisoformat(data["prepay_date"])

    buttons = [
        [
            InlineKeyboardButton(text="✅ Подтвердить", callback_data="prepay:confirm"),
            InlineKeyboardButton(text="❌ Отмена", callback_data="prepay:cancel"),
        ]
    ]

    await state.set_state(PrepaymentStates.confirming)
    await message.answer(
        f"💵 Предоплата\n\n"
        f"📅 Дата заезда: {prepay_date.strftime('%d.%m.%Y')}\n"
        f"🏠 Объект: {data['prepay_property_name']}\n"
        f"💰 Сумма: {format_amount(amount)}\n\n"
        f"Подтвердить?",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
    )


# ── Confirm → save ────────────────────────────────────────────────


@router.callback_query(F.data == "prepay:confirm", PrepaymentStates.confirming)
async def on_prepay_confirm(callback: types.CallbackQuery, state: FSMContext):
    """Save prepayment entry."""
    data = await state.get_data()
    lang = data.get("lang", "ru")
    prepay_date = date.fromisoformat(data["prepay_date"])
    user_id = data["user_id"]
    business_unit = BusinessUnit(data["business_unit"])

    async with async_session() as session:
        # Get or create a draft report for the prepayment date
        from sqlalchemy import and_
        result = await session.execute(
            select(StructuredReport).where(
                and_(
                    StructuredReport.submitted_by == user_id,
                    StructuredReport.report_date == prepay_date,
                    StructuredReport.business_unit == business_unit,
                    StructuredReport.status == ReportStatus.DRAFT,
                )
            )
        )
        report = result.scalar_one_or_none()

        if not report:
            report = StructuredReport(
                report_date=prepay_date,
                business_unit=business_unit,
                status=ReportStatus.DRAFT,
                submitted_by=user_id,
                total_income=Decimal(0),
                total_expense=Decimal(0),
                previous_balance=Decimal(0),
            )
            session.add(report)
            await session.flush()

        # Create income entry as prepayment
        amount = Decimal(data["prepay_amount"])
        entry = IncomeEntry(
            report_id=report.id,
            property_id=data["prepay_property_id"],
            payment_method=PaymentMethod.PREPAYMENT,
            amount=amount,
            num_days=0,
        )
        session.add(entry)

        # Update report totals
        report.total_income = (report.total_income or Decimal(0)) + amount
        await session.commit()

    # Clear state and return to main menu
    await state.clear()

    user = await get_user(callback.from_user.id)
    lang = user.language.value.lower() if user else "ru"
    section = user.active_section.value.lower() if user else "resort"
    section_name = get_text(f"section_{section}", lang)

    await callback.message.edit_text(
        f"✅ Предоплата {format_amount(data['prepay_amount'])} сохранена\n"
        f"📅 {prepay_date.strftime('%d.%m.%Y')} — {data['prepay_property_name']}\n\n"
        f"{get_text('main_menu', lang, section=section_name)}",
        reply_markup=main_menu_keyboard(lang, current_section=section),
    )
    await callback.answer()


# ── Cancel ────────────────────────────────────────────────────────


@router.callback_query(F.data == "prepay:cancel")
async def on_prepay_cancel(callback: types.CallbackQuery, state: FSMContext):
    """Cancel prepayment flow and return to main menu."""
    await state.clear()

    user = await get_user(callback.from_user.id)
    if not user:
        await callback.answer()
        return

    lang = user.language.value.lower()
    section = user.active_section.value.lower()
    section_name = get_text(f"section_{section}", lang)

    await callback.message.edit_text(
        get_text("main_menu", lang, section=section_name),
        reply_markup=main_menu_keyboard(lang, current_section=section),
    )
    await callback.answer()
