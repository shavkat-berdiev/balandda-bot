"""Structured report entry handler with button-driven forms.

Flow:
1. User taps "action:new_report" callback
2. Check user is registered (any role)
3. Create draft StructuredReport for today
4. Show report action menu (accommodations, services, minibar, expenses, preview, finalize)
5. Each entry type has its own flow with confirmations
6. After each entry, return to report action menu
7. On finalize: mark as SUBMITTED, send summary, notify admin
"""

import logging
from datetime import date, timedelta
from decimal import Decimal

from aiogram import F, Router, types
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import and_, select

from bot.keyboards.main import main_menu_keyboard
from bot.locales import get_text
from db.database import async_session
from db.enums import (
    DiscountReason,
    DiscountType,
    DISCOUNT_REASON_LABELS,
    DISCOUNT_TYPE_LABELS,
    ExpenseCategory,
    EXPENSE_CATEGORY_LABELS,
    PaymentMethod,
    PAYMENT_METHOD_LABELS,
    ReportStatus,
    RestaurantIncomeCategory,
    RESTAURANT_INCOME_LABELS,
)
from db.models import (
    DiscountReason as DiscountReasonEnum,
    DiscountType as DiscountTypeEnum,
    ExpenseEntry,
    IncomeEntry,
    MinibarItem,
    Property,
    ReportStatus as ReportStatusEnum,
    ServiceItem,
    StaffMember,
    StructuredReport,
    User,
)

router = Router()
logger = logging.getLogger(__name__)


class NewReportStates(StatesGroup):
    """FSM states for structured report entry."""
    choosing_date = State()
    choosing_action = State()
    choosing_property = State()
    choosing_service = State()
    choosing_minibar = State()
    choosing_restaurant_category = State()
    entering_payment = State()
    entering_amount = State()
    entering_discount = State()
    entering_discount_value = State()
    entering_days = State()
    entering_minibar_qty = State()
    entering_restaurant_note = State()
    confirming_entry = State()


async def get_user(telegram_id: int) -> User | None:
    """Get user from database."""
    async with async_session() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == telegram_id)
        )
        return result.scalar_one_or_none()


async def get_or_create_draft_report(user_id: int, report_date: date, business_unit) -> StructuredReport:
    """Get or create a draft report for today."""
    async with async_session() as session:
        result = await session.execute(
            select(StructuredReport).where(
                and_(
                    StructuredReport.submitted_by == user_id,
                    StructuredReport.report_date == report_date,
                    StructuredReport.business_unit == business_unit,
                    StructuredReport.status == ReportStatusEnum.DRAFT,
                )
            )
        )
        report = result.scalar_one_or_none()

        if not report:
            report = StructuredReport(
                report_date=report_date,
                business_unit=business_unit,
                status=ReportStatusEnum.DRAFT,
                submitted_by=user_id,
                total_income=Decimal(0),
                total_expense=Decimal(0),
                previous_balance=Decimal(0),
            )
            session.add(report)
            await session.commit()
            await session.refresh(report)

        return report


def format_amount(amount: float | Decimal | str) -> str:
    """Format amount with dot separators (e.g., 3.200.000)."""
    if isinstance(amount, str):
        amount = float(amount)
    elif isinstance(amount, Decimal):
        amount = float(amount)
    return f"{amount:,.0f}".replace(",", ".")


async def build_report_action_menu(lang: str, business_unit: str = "RESORT") -> InlineKeyboardMarkup:
    """Build the main report action menu.

    Resort: accommodation, service, minibar, expense
    Restaurant: income (simple), expense
    """
    if business_unit == "RESTAURANT":
        buttons = [
            [InlineKeyboardButton(text="💰 Доход", callback_data="rpt:add_restaurant_income")],
            [InlineKeyboardButton(text="💸 Расход", callback_data="rpt:add_expense")],
            [InlineKeyboardButton(text="👁 Предпросмотр", callback_data="rpt:preview")],
            [InlineKeyboardButton(text="✅ Завершить отчёт", callback_data="rpt:finalize")],
            [InlineKeyboardButton(text=f"❌ {get_text('btn_cancel', lang)}", callback_data="rpt:cancel")],
        ]
    else:
        buttons = [
            [InlineKeyboardButton(text="🏠 Заселение", callback_data="rpt:add_accommodation")],
            [InlineKeyboardButton(text="💆 Массаж / SPA", callback_data="rpt:add_service")],
            [InlineKeyboardButton(text="🍹 Мини бар", callback_data="rpt:add_minibar")],
            [InlineKeyboardButton(text="💸 Расход", callback_data="rpt:add_expense")],
            [InlineKeyboardButton(text="👁 Предпросмотр", callback_data="rpt:preview")],
            [InlineKeyboardButton(text="✅ Завершить отчёт", callback_data="rpt:finalize")],
            [InlineKeyboardButton(text=f"❌ {get_text('btn_cancel', lang)}", callback_data="rpt:cancel")],
        ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


# ────────────────────────────────────────────────────────────────────────
# DATE PICKER HELPERS
# ────────────────────────────────────────────────────────────────────────

DAY_NAMES_RU = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
MONTH_NAMES_RU = [
    "", "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
    "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь",
]

MAX_PAST_DAYS = 30
MAX_FUTURE_DAYS = 90


def _build_date_picker(year: int, month: int) -> InlineKeyboardMarkup:
    """Build a calendar-style date picker for the given month."""
    import calendar

    today = date.today()
    min_date = today - timedelta(days=MAX_PAST_DAYS)
    max_date = today + timedelta(days=MAX_FUTURE_DAYS)

    buttons = []

    # Month/year header with nav arrows
    buttons.append([
        InlineKeyboardButton(text="◀️", callback_data=f"cal:prev:{year}:{month}"),
        InlineKeyboardButton(text=f"{MONTH_NAMES_RU[month]} {year}", callback_data="cal:noop"),
        InlineKeyboardButton(text="▶️", callback_data=f"cal:next:{year}:{month}"),
    ])

    # Day-of-week header
    buttons.append([
        InlineKeyboardButton(text=d, callback_data="cal:noop") for d in DAY_NAMES_RU
    ])

    # Day grid
    cal = calendar.monthcalendar(year, month)
    for week in cal:
        row = []
        for day_num in week:
            if day_num == 0:
                row.append(InlineKeyboardButton(text=" ", callback_data="cal:noop"))
            else:
                d = date(year, month, day_num)
                if d < min_date or d > max_date:
                    row.append(InlineKeyboardButton(text="·", callback_data="cal:noop"))
                elif d == today:
                    row.append(InlineKeyboardButton(
                        text=f"[{day_num}]",
                        callback_data=f"cal:day:{d.isoformat()}",
                    ))
                else:
                    row.append(InlineKeyboardButton(
                        text=str(day_num),
                        callback_data=f"cal:day:{d.isoformat()}",
                    ))
        buttons.append(row)

    # Cancel
    buttons.append([InlineKeyboardButton(text="❌ Отмена", callback_data="rpt:cancel")])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


# ────────────────────────────────────────────────────────────────────────
# ENTRY POINT: Start new report → date selection
# ────────────────────────────────────────────────────────────────────────


@router.callback_query(F.data == "action:new_report")
async def on_new_report(callback: types.CallbackQuery, state: FSMContext):
    """Start a new structured report — show date picker."""
    user = await get_user(callback.from_user.id)
    if not user:
        await callback.answer("Пользователь не найден")
        return

    lang = user.language.value.lower()
    await state.update_data(lang=lang, user_id=user.id, business_unit=user.active_section.value)

    today = date.today()
    yesterday = today - timedelta(days=1)

    # Quick-pick buttons + calendar
    buttons = [
        [
            InlineKeyboardButton(
                text=f"📅 Сегодня ({today.strftime('%d.%m')})",
                callback_data=f"cal:day:{today.isoformat()}",
            ),
        ],
        [
            InlineKeyboardButton(
                text=f"📅 Вчера ({yesterday.strftime('%d.%m')})",
                callback_data=f"cal:day:{yesterday.isoformat()}",
            ),
        ],
        [
            InlineKeyboardButton(
                text="📆 Выбрать дату...",
                callback_data=f"cal:show:{today.year}:{today.month}",
            ),
        ],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="rpt:cancel")],
    ]

    await state.set_state(NewReportStates.choosing_date)
    await callback.message.edit_text(
        "📝 Новый отчёт\n\nВыберите дату отчёта:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("cal:show:"), NewReportStates.choosing_date)
async def on_show_calendar(callback: types.CallbackQuery, state: FSMContext):
    """Show full calendar picker."""
    parts = callback.data.split(":")
    year, month = int(parts[2]), int(parts[3])
    keyboard = _build_date_picker(year, month)
    await callback.message.edit_text(
        "📆 Выберите дату:",
        reply_markup=keyboard,
    )
    await callback.answer()


@router.callback_query(F.data.startswith("cal:prev:"), NewReportStates.choosing_date)
async def on_cal_prev(callback: types.CallbackQuery, state: FSMContext):
    """Navigate calendar backwards."""
    parts = callback.data.split(":")
    year, month = int(parts[2]), int(parts[3])
    month -= 1
    if month < 1:
        month = 12
        year -= 1
    keyboard = _build_date_picker(year, month)
    await callback.message.edit_text("📆 Выберите дату:", reply_markup=keyboard)
    await callback.answer()


@router.callback_query(F.data.startswith("cal:next:"), NewReportStates.choosing_date)
async def on_cal_next(callback: types.CallbackQuery, state: FSMContext):
    """Navigate calendar forwards."""
    parts = callback.data.split(":")
    year, month = int(parts[2]), int(parts[3])
    month += 1
    if month > 12:
        month = 1
        year += 1
    keyboard = _build_date_picker(year, month)
    await callback.message.edit_text("📆 Выберите дату:", reply_markup=keyboard)
    await callback.answer()


@router.callback_query(F.data == "cal:noop", NewReportStates.choosing_date)
async def on_cal_noop(callback: types.CallbackQuery, state: FSMContext):
    """Ignore taps on header/empty cells."""
    await callback.answer()


@router.callback_query(F.data.startswith("cal:day:"), NewReportStates.choosing_date)
async def on_date_selected(callback: types.CallbackQuery, state: FSMContext):
    """Date selected — create/get draft report and show action menu."""
    date_str = callback.data.split(":", 2)[2]
    selected_date = date.fromisoformat(date_str)

    data = await state.get_data()
    lang = data.get("lang", "ru")
    user_id = data["user_id"]

    # Get user for business unit
    user = await get_user(callback.from_user.id)
    if not user:
        await callback.answer("Пользователь не найден")
        return

    report = await get_or_create_draft_report(user_id, selected_date, user.active_section)
    bu = data.get("business_unit", user.active_section.value)
    await state.update_data(report_id=report.id, report_date=date_str)
    await state.set_state(NewReportStates.choosing_action)

    keyboard = await build_report_action_menu(lang, business_unit=bu)
    await callback.message.edit_text(
        f"📝 Отчёт на {selected_date.strftime('%d.%m.%Y')}\n\n"
        f"Выберите действие:",
        reply_markup=keyboard,
    )
    await callback.answer()


# ────────────────────────────────────────────────────────────────────────
# ACCOMMODATION FLOW
# ────────────────────────────────────────────────────────────────────────


@router.callback_query(F.data == "rpt:add_accommodation", NewReportStates.choosing_action)
async def on_add_accommodation(callback: types.CallbackQuery, state: FSMContext):
    """Show property selection."""
    data = await state.get_data()
    lang = data.get("lang", "ru")

    # Clear any leftover entry data from previous flows
    await state.update_data(
        current_property=None, base_price=None, amount=None,
        payment_method=None, discount_type=None, discount_value=None,
        discount_reason=None, num_days=None, current_service=None,
        service_price=None, current_minibar=None, minibar_price=None,
        quantity=None, entry_type="accommodation",
    )

    async with async_session() as session:
        result = await session.execute(
            select(Property)
            .where(Property.is_active == True)
            .order_by(Property.sort_order)
        )
        properties = result.scalars().all()

    # Build 2-column grid
    buttons = []
    for prop in properties:
        emoji = prop.emoji or "🏠"
        label = f"{emoji} {prop.name_ru}"
        buttons.append(InlineKeyboardButton(text=label, callback_data=f"prop:{prop.id}"))

    # Create 2-column layout
    keyboard_buttons = []
    for i in range(0, len(buttons), 2):
        row = [buttons[i]]
        if i + 1 < len(buttons):
            row.append(buttons[i + 1])
        keyboard_buttons.append(row)

    keyboard_buttons.append([
        InlineKeyboardButton(text=f"❌ {get_text('btn_cancel', lang)}", callback_data="rpt:cancel")
    ])

    await state.set_state(NewReportStates.choosing_property)
    await callback.message.edit_text(
        "🏠 Выберите жилую единицу:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard_buttons),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("prop:"), NewReportStates.choosing_property)
async def on_property_selected(callback: types.CallbackQuery, state: FSMContext):
    """Property selected, show prepayment info and ask for payment method."""
    try:
        prop_id = int(callback.data.split(":")[1])
        data = await state.get_data()
        lang = data.get("lang", "ru")
        report_date_str = data.get("report_date", date.today().isoformat())
        report_date = date.fromisoformat(report_date_str)

        async with async_session() as session:
            # Get property
            result = await session.execute(select(Property).where(Property.id == prop_id))
            prop = result.scalar_one_or_none()

            if not prop:
                await callback.answer("Объект не найден")
                return

            # Check for existing prepayments on this property
            # Look for PREPAYMENT entries linked to this property across all reports
            # within a reasonable window (30 days before the report date)
            try:
                prepay_query = (
                    select(IncomeEntry)
                    .join(StructuredReport)
                    .where(
                        IncomeEntry.property_id == prop_id,
                        IncomeEntry.payment_method == PaymentMethod.PREPAYMENT,
                        StructuredReport.report_date >= report_date - timedelta(days=30),
                        StructuredReport.report_date <= report_date,
                    )
                )
                prepay_result = await session.execute(prepay_query)
                prepayments = prepay_result.scalars().all()
            except Exception as e:
                logger.error(f"Prepayment query failed: {e}")
                prepayments = []

        await state.update_data(current_property=prop_id, base_price=float(prop.price_weekday))

        # Build info text
        info = f"💳 {prop.name_ru}\nБазовая цена: {format_amount(prop.price_weekday)}\n"

        if prepayments:
            total_prepaid = sum(float(p.amount) for p in prepayments)
            info += f"\n💵 Предоплата: {format_amount(total_prepaid)} ({len(prepayments)} платеж(ей))\n"

        info += "\nВыберите способ оплаты:"

        # Show payment methods
        buttons = []
        for method in PaymentMethod:
            label = PAYMENT_METHOD_LABELS.get(method, method.value)
            buttons.append([InlineKeyboardButton(text=label, callback_data=f"pm:{method.value}")])

        buttons.append([InlineKeyboardButton(text=f"❌ {get_text('btn_cancel', lang)}", callback_data="rpt:cancel")])

        await state.set_state(NewReportStates.entering_payment)
        await callback.message.edit_text(info, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
        await callback.answer()
    except Exception as e:
        logger.error(f"on_property_selected error: {e}", exc_info=True)
        await callback.answer(f"Ошибка: {str(e)[:100]}", show_alert=True)


@router.callback_query(F.data.startswith("pm:"), NewReportStates.entering_payment)
async def on_payment_method_selected(callback: types.CallbackQuery, state: FSMContext):
    """Payment method selected, ask for amount."""
    method = callback.data.split(":")[1]
    data = await state.get_data()
    lang = data.get("lang", "ru")
    base_price = data.get("base_price", 0)

    await state.update_data(payment_method=method)
    await state.set_state(NewReportStates.entering_amount)

    await callback.message.edit_text(
        f"💰 Введите сумму\n\nБазовая цена: {format_amount(base_price)}\n\n"
        f"(отправьте числовое значение):"
    )
    await callback.answer()


@router.message(NewReportStates.entering_amount)
async def on_amount_entered(message: types.Message, state: FSMContext):
    """Amount entered, ask for discount (resort) or payment (restaurant)."""
    data = await state.get_data()
    lang = data.get("lang", "ru")

    # Parse amount
    raw = message.text.strip().replace(" ", "").replace(",", "").replace(".", "")
    try:
        amount = Decimal(raw)
        if amount <= 0:
            raise ValueError
    except (ValueError, Exception):
        await message.answer(f"❌ Введите корректную сумму (только цифры)")
        return

    await state.update_data(amount=str(amount))

    # For restaurant income: skip discounts, go to payment method
    if data.get("entry_type") == "restaurant_income":
        buttons = []
        for method in PaymentMethod:
            if method == PaymentMethod.PREPAYMENT:
                continue  # Skip prepayment for restaurant income
            label = PAYMENT_METHOD_LABELS.get(method, method.value)
            buttons.append([InlineKeyboardButton(text=label, callback_data=f"rest_pm:{method.value}")])
        buttons.append([InlineKeyboardButton(text=f"❌ {get_text('btn_cancel', lang)}", callback_data="rpt:cancel")])

        await state.set_state(NewReportStates.entering_payment)
        await message.answer(
            f"💰 Сумма: {format_amount(float(amount))}\n\nВыберите способ оплаты:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        )
        return

    # For resort accommodation: ask about discount
    buttons = [
        [InlineKeyboardButton(text="Нет скидки", callback_data="discount:none")],
        [InlineKeyboardButton(text="% Процент", callback_data="discount:percentage")],
        [InlineKeyboardButton(text="💰 Фиксированная", callback_data="discount:fixed")],
        [InlineKeyboardButton(text=f"❌ {get_text('btn_cancel', lang)}", callback_data="rpt:cancel")],
    ]

    await state.set_state(NewReportStates.entering_discount)
    await message.answer(
        f"Скидка на сумму {format_amount(float(amount))}?",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
    )


@router.callback_query(F.data.startswith("discount:"), NewReportStates.entering_discount)
async def on_discount_choice(callback: types.CallbackQuery, state: FSMContext):
    """Handle discount choice."""
    choice = callback.data.split(":")[1]
    data = await state.get_data()
    lang = data.get("lang", "ru")

    if choice == "none":
        await state.update_data(discount_type=None, discount_value=0)
        # Ask for days
        await _ask_for_days(callback.message, state)
    else:
        discount_type = "PERCENTAGE" if choice == "percentage" else "FIXED_AMOUNT"
        await state.update_data(discount_type=discount_type)
        await state.set_state(NewReportStates.entering_discount_value)

        prompt = "Введите размер скидки (% или сумма):" if choice == "percentage" else "Введите размер скидки (сумма):"
        await callback.message.edit_text(prompt)

    await callback.answer()


@router.message(NewReportStates.entering_discount_value)
async def on_discount_value(message: types.Message, state: FSMContext):
    """Discount value entered, ask for reason."""
    data = await state.get_data()
    lang = data.get("lang", "ru")

    try:
        value = Decimal(message.text.strip())
        if value <= 0:
            raise ValueError
    except (ValueError, Exception):
        await message.answer("❌ Введите корректное значение скидки")
        return

    await state.update_data(discount_value=str(value))

    # Ask for discount reason
    buttons = []
    for reason in DiscountReason:
        label = DISCOUNT_REASON_LABELS.get(reason, reason.value)
        buttons.append([InlineKeyboardButton(text=label, callback_data=f"disc_reason:{reason.value}")])

    buttons.append([InlineKeyboardButton(text=f"❌ {get_text('btn_cancel', lang)}", callback_data="rpt:cancel")])

    await state.set_state(NewReportStates.entering_discount)
    await message.answer(
        "Причина скидки:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
    )


@router.callback_query(F.data.startswith("disc_reason:"), NewReportStates.entering_discount)
async def on_discount_reason(callback: types.CallbackQuery, state: FSMContext):
    """Discount reason selected, ask for days."""
    reason = callback.data.split(":")[1]
    await state.update_data(discount_reason=reason)
    await _ask_for_days(callback.message, state)
    await callback.answer()


async def _ask_for_days(message: types.Message, state: FSMContext, edit: bool = True):
    """Helper to ask for number of days."""
    data = await state.get_data()
    lang = data.get("lang", "ru")

    buttons = [
        [
            InlineKeyboardButton(text="1", callback_data="days:1"),
            InlineKeyboardButton(text="2", callback_data="days:2"),
            InlineKeyboardButton(text="3", callback_data="days:3"),
        ],
        [InlineKeyboardButton(text="Другое", callback_data="days:other")],
        [InlineKeyboardButton(text=f"❌ {get_text('btn_cancel', lang)}", callback_data="rpt:cancel")],
    ]

    await state.set_state(NewReportStates.entering_days)
    if edit:
        await message.edit_text(
            "Количество дней:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        )
    else:
        await message.answer(
            "Количество дней:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        )


@router.callback_query(F.data.startswith("days:"), NewReportStates.entering_days)
async def on_days_selected(callback: types.CallbackQuery, state: FSMContext):
    """Days selected or needs input."""
    days_str = callback.data.split(":")[1]
    data = await state.get_data()
    lang = data.get("lang", "ru")

    if days_str == "other":
        await callback.message.edit_text("Введите количество дней:")
        await callback.answer()
    else:
        await state.update_data(num_days=int(days_str))
        await _show_accommodation_confirmation(callback.message, state, edit=True)
        await callback.answer()


@router.message(NewReportStates.entering_days)
async def on_days_entered(message: types.Message, state: FSMContext):
    """Days entered as text."""
    try:
        days = int(message.text.strip())
        if days <= 0:
            raise ValueError
    except (ValueError, Exception):
        await message.answer("❌ Введите корректное количество дней")
        return

    await state.update_data(num_days=days)
    await _show_accommodation_confirmation(message, state, edit=False)


async def _show_accommodation_confirmation(message: types.Message, state: FSMContext, edit: bool = True):
    """Show confirmation for accommodation entry."""
    data = await state.get_data()
    lang = data.get("lang", "ru")

    # Get property name
    async with async_session() as session:
        result = await session.execute(
            select(Property).where(Property.id == data["current_property"])
        )
        prop = result.scalar_one_or_none()

    if not prop:
        await message.answer("❌ Ошибка: объект не найден")
        return

    amount = Decimal(data["amount"])
    pm_value = data["payment_method"]
    pm_label = PAYMENT_METHOD_LABELS.get(PaymentMethod(pm_value), pm_value)

    summary = f"📝 Заселение\n\n{prop.name_ru}\n"
    summary += f"Сумма: {format_amount(amount)}\n"
    summary += f"Способ оплаты: {pm_label}\n"

    if data.get("discount_type"):
        disc_val = data.get("discount_value", 0)
        if data["discount_type"] == "PERCENTAGE":
            summary += f"Скидка: {disc_val}%\n"
        else:
            summary += f"Скидка: {format_amount(disc_val)}\n"
        if data.get("discount_reason"):
            disc_reason_label = DISCOUNT_REASON_LABELS.get(
                DiscountReason(data["discount_reason"]), data["discount_reason"]
            )
            summary += f"Причина: {disc_reason_label}\n"

    summary += f"Количество дней: {data['num_days']}\n"

    buttons = [
        [
            InlineKeyboardButton(text="✅ Подтвердить", callback_data="acc:confirm"),
            InlineKeyboardButton(text="❌ Отмена", callback_data="rpt:cancel"),
        ]
    ]

    await state.set_state(NewReportStates.confirming_entry)
    if edit:
        await message.edit_text(summary, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    else:
        await message.answer(summary, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))


@router.callback_query(F.data == "acc:confirm", NewReportStates.confirming_entry)
async def on_accommodation_confirm(callback: types.CallbackQuery, state: FSMContext):
    """Save accommodation entry and return to menu."""
    data = await state.get_data()
    lang = data.get("lang", "ru")
    report_id = data["report_id"]

    async with async_session() as session:
        # Create IncomeEntry
        entry = IncomeEntry(
            report_id=report_id,
            property_id=data["current_property"],
            payment_method=PaymentMethod(data["payment_method"]),
            amount=Decimal(data["amount"]),
            num_days=data.get("num_days", 1),
            discount_type=DiscountTypeEnum(data["discount_type"]) if data.get("discount_type") else None,
            discount_value=Decimal(data["discount_value"]) if data.get("discount_value") else None,
            discount_reason=DiscountReasonEnum(data["discount_reason"]) if data.get("discount_reason") else None,
        )
        session.add(entry)

        # Update report totals
        report = await session.get(StructuredReport, report_id)
        if report:
            report.total_income = (report.total_income or Decimal(0)) + Decimal(data["amount"])
            await session.merge(report)

        await session.commit()

    # Clear entry data
    await state.update_data(
        current_property=None,
        base_price=None,
        amount=None,
        payment_method=None,
        discount_type=None,
        discount_value=None,
        discount_reason=None,
        num_days=None,
    )

    await state.set_state(NewReportStates.choosing_action)
    keyboard = await build_report_action_menu(lang, business_unit=data.get("business_unit", "RESORT"))
    await callback.message.edit_text(
        "✅ Запись добавлена\n\nВыберите действие:",
        reply_markup=keyboard,
    )
    await callback.answer()


# ────────────────────────────────────────────────────────────────────────
# RESTAURANT INCOME FLOW (simple: category → amount → payment → note → confirm)
# ────────────────────────────────────────────────────────────────────────


@router.callback_query(F.data == "rpt:add_restaurant_income", NewReportStates.choosing_action)
async def on_add_restaurant_income(callback: types.CallbackQuery, state: FSMContext):
    """Show restaurant income category selection."""
    data = await state.get_data()
    lang = data.get("lang", "ru")

    # Clear leftover entry data
    await state.update_data(
        current_property=None, base_price=None, amount=None,
        payment_method=None, discount_type=None, discount_value=None,
        discount_reason=None, num_days=None, current_service=None,
        service_price=None, current_minibar=None, minibar_price=None,
        quantity=None, restaurant_category=None, restaurant_note=None,
        entry_type="restaurant_income",
    )

    buttons = []
    for cat in RestaurantIncomeCategory:
        label = RESTAURANT_INCOME_LABELS.get(cat, cat.value)
        buttons.append([InlineKeyboardButton(text=label, callback_data=f"rest_cat:{cat.value}")])

    buttons.append([InlineKeyboardButton(text=f"❌ {get_text('btn_cancel', lang)}", callback_data="rpt:cancel")])

    await state.set_state(NewReportStates.choosing_restaurant_category)
    await callback.message.edit_text(
        "💰 Выберите категорию дохода:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("rest_cat:"), NewReportStates.choosing_restaurant_category)
async def on_restaurant_category_selected(callback: types.CallbackQuery, state: FSMContext):
    """Restaurant income category selected → ask for amount."""
    cat_value = callback.data.split(":")[1]
    data = await state.get_data()
    lang = data.get("lang", "ru")

    cat = RestaurantIncomeCategory(cat_value)
    cat_label = RESTAURANT_INCOME_LABELS.get(cat, cat_value)

    await state.update_data(restaurant_category=cat_value, restaurant_category_label=cat_label)
    await state.set_state(NewReportStates.entering_amount)

    await callback.message.edit_text(
        f"💰 {cat_label}\n\nВведите сумму (UZS):"
    )
    await callback.answer()


@router.callback_query(F.data.startswith("rest_pm:"), NewReportStates.entering_payment)
async def on_restaurant_payment_selected(callback: types.CallbackQuery, state: FSMContext):
    """Restaurant income payment method selected → ask for note."""
    method = callback.data.split(":")[1]
    data = await state.get_data()
    lang = data.get("lang", "ru")

    await state.update_data(payment_method=method)
    await state.set_state(NewReportStates.entering_restaurant_note)

    buttons = [
        [InlineKeyboardButton(text="⏩ Пропустить", callback_data="rest_note:skip")],
        [InlineKeyboardButton(text=f"❌ {get_text('btn_cancel', lang)}", callback_data="rpt:cancel")],
    ]

    await callback.message.edit_text(
        "📝 Добавьте комментарий (или пропустите):",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
    )
    await callback.answer()


@router.callback_query(F.data == "rest_note:skip", NewReportStates.entering_restaurant_note)
async def on_restaurant_note_skip(callback: types.CallbackQuery, state: FSMContext):
    """Note skipped."""
    await state.update_data(restaurant_note="")
    await _show_restaurant_income_confirmation(callback.message, state, edit=True)
    await callback.answer()


@router.message(NewReportStates.entering_restaurant_note)
async def on_restaurant_note_entered(message: types.Message, state: FSMContext):
    """Note entered."""
    await state.update_data(restaurant_note=message.text.strip())
    await _show_restaurant_income_confirmation(message, state, edit=False)


async def _show_restaurant_income_confirmation(message: types.Message, state: FSMContext, edit: bool = True):
    """Show confirmation for restaurant income entry."""
    data = await state.get_data()
    lang = data.get("lang", "ru")

    amount = Decimal(data["amount"])
    cat_label = data.get("restaurant_category_label", "Доход")
    pm_label = PAYMENT_METHOD_LABELS.get(PaymentMethod(data["payment_method"]), data["payment_method"])
    note = data.get("restaurant_note", "")

    summary = f"📝 Доход (ресторан)\n\n"
    summary += f"Категория: {cat_label}\n"
    summary += f"Сумма: {format_amount(amount)}\n"
    summary += f"Способ оплаты: {pm_label}\n"
    if note:
        summary += f"Комментарий: {note}\n"

    buttons = [
        [
            InlineKeyboardButton(text="✅ Подтвердить", callback_data="rest:confirm"),
            InlineKeyboardButton(text="❌ Отмена", callback_data="rpt:cancel"),
        ]
    ]

    await state.set_state(NewReportStates.confirming_entry)
    if edit:
        await message.edit_text(summary, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    else:
        await message.answer(summary, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))


@router.callback_query(F.data == "rest:confirm", NewReportStates.confirming_entry)
async def on_restaurant_income_confirm(callback: types.CallbackQuery, state: FSMContext):
    """Save restaurant income entry."""
    data = await state.get_data()
    lang = data.get("lang", "ru")
    report_id = data["report_id"]

    async with async_session() as session:
        entry = IncomeEntry(
            report_id=report_id,
            restaurant_category=RestaurantIncomeCategory(data["restaurant_category"]),
            payment_method=PaymentMethod(data["payment_method"]),
            amount=Decimal(data["amount"]),
            note=data.get("restaurant_note") or None,
        )
        session.add(entry)

        report = await session.get(StructuredReport, report_id)
        if report:
            report.total_income = (report.total_income or Decimal(0)) + Decimal(data["amount"])
            await session.merge(report)

        await session.commit()

    # Clear entry data
    await state.update_data(
        restaurant_category=None, restaurant_category_label=None,
        restaurant_note=None, amount=None, payment_method=None,
    )

    await state.set_state(NewReportStates.choosing_action)
    keyboard = await build_report_action_menu(lang, business_unit=data.get("business_unit", "RESTAURANT"))
    await callback.message.edit_text(
        "✅ Доход добавлен\n\nВыберите действие:",
        reply_markup=keyboard,
    )
    await callback.answer()


# ────────────────────────────────────────────────────────────────────────
# SERVICE FLOW
# ────────────────────────────────────────────────────────────────────────


@router.callback_query(F.data == "rpt:add_service", NewReportStates.choosing_action)
async def on_add_service(callback: types.CallbackQuery, state: FSMContext):
    """Show service selection."""
    data = await state.get_data()
    lang = data.get("lang", "ru")

    # Clear any leftover entry data from previous flows
    await state.update_data(
        current_property=None, base_price=None, amount=None,
        payment_method=None, discount_type=None, discount_value=None,
        discount_reason=None, num_days=None, current_service=None,
        service_price=None, current_minibar=None, minibar_price=None,
        quantity=None, entry_type="service",
    )

    async with async_session() as session:
        result = await session.execute(
            select(ServiceItem)
            .where(ServiceItem.is_active == True)
            .order_by(ServiceItem.sort_order)
        )
        services = result.scalars().all()

    buttons = []
    for svc in services:
        label = f"{svc.name_ru} - {format_amount(svc.price)}"
        buttons.append([InlineKeyboardButton(text=label, callback_data=f"svc:{svc.id}")])

    buttons.append([InlineKeyboardButton(text=f"❌ {get_text('btn_cancel', lang)}", callback_data="rpt:cancel")])

    await state.set_state(NewReportStates.choosing_service)
    await callback.message.edit_text(
        "💆 Выберите услугу:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("svc:"), NewReportStates.choosing_service)
async def on_service_selected(callback: types.CallbackQuery, state: FSMContext):
    """Service selected, ask for payment method."""
    svc_id = int(callback.data.split(":")[1])
    data = await state.get_data()
    lang = data.get("lang", "ru")

    async with async_session() as session:
        result = await session.execute(select(ServiceItem).where(ServiceItem.id == svc_id))
        svc = result.scalar_one_or_none()

    if not svc:
        await callback.answer("Услуга не найдена")
        return

    await state.update_data(
        current_service=svc_id,
        service_price=float(svc.price),
        amount=str(svc.price),
    )

    # Show payment methods
    buttons = []
    for method in PaymentMethod:
        label = PAYMENT_METHOD_LABELS.get(method, method.value)
        buttons.append([InlineKeyboardButton(text=label, callback_data=f"svc_pm:{method.value}")])

    buttons.append([InlineKeyboardButton(text=f"❌ {get_text('btn_cancel', lang)}", callback_data="rpt:cancel")])

    await state.set_state(NewReportStates.entering_payment)
    await callback.message.edit_text(
        f"💳 {svc.name_ru}\nЦена: {format_amount(svc.price)}\n\nВыберите способ оплаты:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("svc_pm:"), NewReportStates.entering_payment)
async def on_service_payment_selected(callback: types.CallbackQuery, state: FSMContext):
    """Service payment method selected."""
    method = callback.data.split(":")[1]
    data = await state.get_data()
    lang = data.get("lang", "ru")

    await state.update_data(payment_method=method)

    # Get service to show confirmation
    async with async_session() as session:
        result = await session.execute(
            select(ServiceItem).where(ServiceItem.id == data["current_service"])
        )
        svc = result.scalar_one_or_none()

    if not svc:
        await callback.answer("Ошибка")
        return

    pm_label = PAYMENT_METHOD_LABELS.get(PaymentMethod(method), method)

    buttons = [
        [
            InlineKeyboardButton(text="✅ Подтвердить", callback_data="svc:confirm"),
            InlineKeyboardButton(text="❌ Отмена", callback_data="rpt:cancel"),
        ]
    ]

    await state.set_state(NewReportStates.confirming_entry)
    await callback.message.edit_text(
        f"💆 {svc.name_ru}\n"
        f"Сумма: {format_amount(svc.price)}\n"
        f"Способ оплаты: {pm_label}\n\n"
        f"Всё верно?",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
    )
    await callback.answer()


@router.callback_query(F.data == "svc:confirm", NewReportStates.confirming_entry)
async def on_service_confirm(callback: types.CallbackQuery, state: FSMContext):
    """Save service entry."""
    data = await state.get_data()
    lang = data.get("lang", "ru")
    report_id = data["report_id"]

    async with async_session() as session:
        entry = IncomeEntry(
            report_id=report_id,
            service_item_id=data["current_service"],
            payment_method=PaymentMethod(data["payment_method"]),
            amount=Decimal(data["amount"]),
        )
        session.add(entry)

        report = await session.get(StructuredReport, report_id)
        if report:
            report.total_income = (report.total_income or Decimal(0)) + Decimal(data["amount"])
            await session.merge(report)

        await session.commit()

    await state.update_data(current_service=None)
    await state.set_state(NewReportStates.choosing_action)
    keyboard = await build_report_action_menu(lang, business_unit=data.get("business_unit", "RESORT"))
    await callback.message.edit_text(
        "✅ Услуга добавлена\n\nВыберите действие:",
        reply_markup=keyboard,
    )
    await callback.answer()


# ────────────────────────────────────────────────────────────────────────
# MINIBAR FLOW
# ────────────────────────────────────────────────────────────────────────


@router.callback_query(F.data == "rpt:add_minibar", NewReportStates.choosing_action)
async def on_add_minibar(callback: types.CallbackQuery, state: FSMContext):
    """Show minibar item selection."""
    data = await state.get_data()
    lang = data.get("lang", "ru")

    # Clear any leftover entry data from previous flows
    await state.update_data(
        current_property=None, base_price=None, amount=None,
        payment_method=None, discount_type=None, discount_value=None,
        discount_reason=None, num_days=None, current_service=None,
        service_price=None, current_minibar=None, minibar_price=None,
        quantity=None, entry_type="minibar",
    )

    async with async_session() as session:
        result = await session.execute(
            select(MinibarItem)
            .where(MinibarItem.is_active == True)
            .order_by(MinibarItem.sort_order)
        )
        items = result.scalars().all()

    buttons = []
    for item in items:
        label = f"{item.name_ru} - {format_amount(item.price)}"
        buttons.append([InlineKeyboardButton(text=label, callback_data=f"mb:{item.id}")])

    buttons.append([InlineKeyboardButton(text=f"❌ {get_text('btn_cancel', lang)}", callback_data="rpt:cancel")])

    await state.set_state(NewReportStates.choosing_minibar)
    await callback.message.edit_text(
        "🍹 Выберите товар мини-бара:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("mb:"), NewReportStates.choosing_minibar)
async def on_minibar_selected(callback: types.CallbackQuery, state: FSMContext):
    """Minibar item selected, ask for quantity."""
    item_id = int(callback.data.split(":")[1])
    data = await state.get_data()
    lang = data.get("lang", "ru")

    async with async_session() as session:
        result = await session.execute(select(MinibarItem).where(MinibarItem.id == item_id))
        item = result.scalar_one_or_none()

    if not item:
        await callback.answer("Товар не найден")
        return

    await state.update_data(current_minibar=item_id, minibar_price=float(item.price))

    buttons = [
        [
            InlineKeyboardButton(text="1", callback_data="mb_qty:1"),
            InlineKeyboardButton(text="2", callback_data="mb_qty:2"),
            InlineKeyboardButton(text="3", callback_data="mb_qty:3"),
            InlineKeyboardButton(text="4", callback_data="mb_qty:4"),
            InlineKeyboardButton(text="5", callback_data="mb_qty:5"),
        ],
        [InlineKeyboardButton(text="Другое", callback_data="mb_qty:other")],
        [InlineKeyboardButton(text=f"❌ {get_text('btn_cancel', lang)}", callback_data="rpt:cancel")],
    ]

    await state.set_state(NewReportStates.entering_minibar_qty)
    await callback.message.edit_text(
        f"🍹 {item.name_ru} - {format_amount(item.price)}\n\nКоличество:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("mb_qty:"), NewReportStates.entering_minibar_qty)
async def on_minibar_qty_selected(callback: types.CallbackQuery, state: FSMContext):
    """Minibar quantity selected."""
    qty_str = callback.data.split(":")[1]
    data = await state.get_data()
    lang = data.get("lang", "ru")

    if qty_str == "other":
        await callback.message.edit_text("Введите количество:")
        await callback.answer()
        return

    qty = int(qty_str)
    amount = Decimal(data["minibar_price"]) * qty
    await state.update_data(quantity=qty, amount=str(amount))

    # Ask for payment method
    buttons = []
    for method in PaymentMethod:
        label = PAYMENT_METHOD_LABELS.get(method, method.value)
        buttons.append([InlineKeyboardButton(text=label, callback_data=f"mb_pm:{method.value}")])

    buttons.append([InlineKeyboardButton(text=f"❌ {get_text('btn_cancel', lang)}", callback_data="rpt:cancel")])

    await state.set_state(NewReportStates.entering_payment)
    await callback.message.edit_text(
        f"💳 Количество: {qty}\nСумма: {format_amount(amount)}\n\nВыберите способ оплаты:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
    )
    await callback.answer()


@router.message(NewReportStates.entering_minibar_qty)
async def on_minibar_qty_entered(message: types.Message, state: FSMContext):
    """Minibar quantity entered as text."""
    data = await state.get_data()
    lang = data.get("lang", "ru")

    try:
        qty = int(message.text.strip())
        if qty <= 0:
            raise ValueError
    except (ValueError, Exception):
        await message.answer("❌ Введите корректное количество")
        return

    amount = Decimal(data["minibar_price"]) * qty
    await state.update_data(quantity=qty, amount=str(amount))

    # Ask for payment method
    buttons = []
    for method in PaymentMethod:
        label = PAYMENT_METHOD_LABELS.get(method, method.value)
        buttons.append([InlineKeyboardButton(text=label, callback_data=f"mb_pm:{method.value}")])

    buttons.append([InlineKeyboardButton(text=f"❌ {get_text('btn_cancel', lang)}", callback_data="rpt:cancel")])

    await state.set_state(NewReportStates.entering_payment)
    await message.answer(
        f"💳 Количество: {qty}\nСумма: {format_amount(amount)}\n\nВыберите способ оплаты:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
    )


@router.callback_query(F.data.startswith("mb_pm:"), NewReportStates.entering_payment)
async def on_minibar_payment_selected(callback: types.CallbackQuery, state: FSMContext):
    """Minibar payment method selected."""
    method = callback.data.split(":")[1]
    data = await state.get_data()
    lang = data.get("lang", "ru")

    await state.update_data(payment_method=method)

    # Get item info
    async with async_session() as session:
        result = await session.execute(
            select(MinibarItem).where(MinibarItem.id == data["current_minibar"])
        )
        item = result.scalar_one_or_none()

    if not item:
        await callback.answer("Ошибка")
        return

    pm_label = PAYMENT_METHOD_LABELS.get(PaymentMethod(method), method)
    amount = Decimal(data["amount"])

    buttons = [
        [
            InlineKeyboardButton(text="✅ Подтвердить", callback_data="mb:confirm"),
            InlineKeyboardButton(text="❌ Отмена", callback_data="rpt:cancel"),
        ]
    ]

    await state.set_state(NewReportStates.confirming_entry)
    await callback.message.edit_text(
        f"🍹 {item.name_ru}\n"
        f"Количество: {data['quantity']}\n"
        f"Сумма: {format_amount(amount)}\n"
        f"Способ оплаты: {pm_label}\n\n"
        f"Всё верно?",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
    )
    await callback.answer()


@router.callback_query(F.data == "mb:confirm", NewReportStates.confirming_entry)
async def on_minibar_confirm(callback: types.CallbackQuery, state: FSMContext):
    """Save minibar entry."""
    data = await state.get_data()
    lang = data.get("lang", "ru")
    report_id = data["report_id"]

    async with async_session() as session:
        entry = IncomeEntry(
            report_id=report_id,
            minibar_item_id=data["current_minibar"],
            payment_method=PaymentMethod(data["payment_method"]),
            amount=Decimal(data["amount"]),
            quantity=data.get("quantity", 1),
        )
        session.add(entry)

        report = await session.get(StructuredReport, report_id)
        if report:
            report.total_income = (report.total_income or Decimal(0)) + Decimal(data["amount"])
            await session.merge(report)

        await session.commit()

    await state.update_data(current_minibar=None, quantity=None)
    await state.set_state(NewReportStates.choosing_action)
    keyboard = await build_report_action_menu(lang, business_unit=data.get("business_unit", "RESORT"))
    await callback.message.edit_text(
        "✅ Товар добавлен\n\nВыберите действие:",
        reply_markup=keyboard,
    )
    await callback.answer()


# ────────────────────────────────────────────────────────────────────────
# PREVIEW
# ────────────────────────────────────────────────────────────────────────


@router.callback_query(F.data == "rpt:preview", NewReportStates.choosing_action)
async def on_preview(callback: types.CallbackQuery, state: FSMContext):
    """Show current report summary."""
    data = await state.get_data()
    lang = data.get("lang", "ru")
    report_id = data["report_id"]

    async with async_session() as session:
        report = await session.get(StructuredReport, report_id)
        if not report:
            await callback.answer("Отчёт не найден")
            return

        # Get all income entries
        from sqlalchemy import select
        result = await session.execute(
            select(IncomeEntry).where(IncomeEntry.report_id == report_id)
        )
        income_entries = result.scalars().all()

        # Get all expense entries
        result = await session.execute(
            select(ExpenseEntry).where(ExpenseEntry.report_id == report_id)
        )
        expense_entries = result.scalars().all()

    # Build preview text
    lines = [f"📝 Предпросмотр отчёта на {report.report_date.strftime('%d.%m.%Y')}"]

    if income_entries:
        lines.append("\n💰 Доходы:")
        # Load all related names in a single session
        async with async_session() as session:
            for entry in income_entries:
                if entry.property_id:
                    prop = await session.get(Property, entry.property_id)
                    lines.append(f"  • {prop.name_ru if prop else 'Объект'}: {format_amount(entry.amount)}")
                elif entry.service_item_id:
                    svc = await session.get(ServiceItem, entry.service_item_id)
                    lines.append(f"  • {svc.name_ru if svc else 'Услуга'}: {format_amount(entry.amount)}")
                elif entry.minibar_item_id:
                    item = await session.get(MinibarItem, entry.minibar_item_id)
                    qty = entry.quantity or 1
                    lines.append(f"  • {item.name_ru if item else 'Товар'} (x{qty}): {format_amount(entry.amount)}")
                else:
                    # Generic income (e.g., restaurant)
                    if entry.restaurant_category:
                        cat_label = RESTAURANT_INCOME_LABELS.get(entry.restaurant_category, entry.restaurant_category.value)
                        lines.append(f"  • {cat_label}: {format_amount(entry.amount)}")
                    else:
                        lines.append(f"  • Доход: {format_amount(entry.amount)}")

    if expense_entries:
        lines.append("\n💸 Расходы:")
        for entry in expense_entries:
            cat_label = EXPENSE_CATEGORY_LABELS.get(entry.expense_category, entry.expense_category.value)
            lines.append(f"  • {cat_label}: {format_amount(entry.amount)}")

    lines.append(f"\n📊 Итого доход: {format_amount(report.total_income or 0)}")
    lines.append(f"📊 Итого расход: {format_amount(report.total_expense or 0)}")
    net = (report.total_income or 0) - (report.total_expense or 0)
    lines.append(f"📊 Чистый доход: {format_amount(net)}")

    back_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ Назад", callback_data="rpt:back")]
    ])

    await callback.message.edit_text("\n".join(lines), reply_markup=back_kb)
    await callback.answer()


@router.callback_query(F.data == "rpt:back", NewReportStates.choosing_action)
async def on_back_to_menu(callback: types.CallbackQuery, state: FSMContext):
    """Back to report menu."""
    data = await state.get_data()
    lang = data.get("lang", "ru")

    keyboard = await build_report_action_menu(lang, business_unit=data.get("business_unit", "RESORT"))
    await callback.message.edit_text(
        "📝 Отчёт\n\nВыберите действие:",
        reply_markup=keyboard,
    )
    await callback.answer()


# ────────────────────────────────────────────────────────────────────────
# FINALIZE
# ────────────────────────────────────────────────────────────────────────


@router.callback_query(F.data == "rpt:finalize", NewReportStates.choosing_action)
async def on_finalize(callback: types.CallbackQuery, state: FSMContext):
    """Mark report as submitted."""
    data = await state.get_data()
    lang = data.get("lang", "ru")
    report_id = data["report_id"]

    async with async_session() as session:
        report = await session.get(StructuredReport, report_id)
        if report:
            report.status = ReportStatusEnum.SUBMITTED
            await session.merge(report)
            await session.commit()

    await state.clear()

    # Show success and back to menu
    user = await get_user(callback.from_user.id)
    if user:
        section_name = get_text(f"section_{user.active_section.value.lower()}", lang)
        await callback.message.edit_text(
            f"✅ Отчёт отправлен!\n\n{get_text('main_menu', lang, section=section_name)}",
            reply_markup=main_menu_keyboard(lang, current_section=user.active_section.value.lower()),
        )
    await callback.answer()


# ────────────────────────────────────────────────────────────────────────
# CANCEL
# ────────────────────────────────────────────────────────────────────────


@router.callback_query(F.data == "rpt:cancel")
async def on_cancel_report(callback: types.CallbackQuery, state: FSMContext):
    """Cancel report and return to main menu."""
    await state.clear()

    user = await get_user(callback.from_user.id)
    if user:
        lang = user.language.value.lower()
        section = user.active_section.value.lower()
        section_name = get_text(f"section_{section}", lang)
        await callback.message.edit_text(
            f"❌ Отменено\n\n{get_text('main_menu', lang, section=section_name)}",
            reply_markup=main_menu_keyboard(lang, current_section=section),
        )
    await callback.answer()
