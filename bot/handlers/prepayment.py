"""Prepayment handler — operator flow for recording advance payments.

Flow:
1. Operator taps "Предоплата" on main menu
2. Enter guest name
3. Select property
4. Pick check-in date (calendar)
5. Pick check-out date (calendar)
6. Select payment method
7. Enter amount
8. Upload screenshot of payment proof
9. Confirm → saves as Prepayment record
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
from db.enums import PaymentMethod, PAYMENT_METHOD_LABELS, PrepaymentStatus
from db.models import (
    Prepayment,
    Property,
    User,
)

router = Router()
logger = logging.getLogger(__name__)

MAX_FUTURE_DAYS = 180
DAY_NAMES_RU = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
MONTH_NAMES_RU = [
    "", "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
    "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь",
]

# Payment methods relevant for prepayments
PREPAY_METHODS = [
    PaymentMethod.CARD_TRANSFER,
    PaymentMethod.PAYME,
    PaymentMethod.CASH,
    PaymentMethod.TERMINAL_VISA,
    PaymentMethod.TERMINAL_UZCARD,
]


class PrepaymentStates(StatesGroup):
    entering_guest_name = State()
    choosing_property = State()
    choosing_checkin_date = State()
    choosing_checkout_date = State()
    choosing_payment_method = State()
    entering_amount = State()
    uploading_screenshot = State()
    confirming = State()


def format_amount(amount) -> str:
    if isinstance(amount, str):
        amount = float(amount)
    elif isinstance(amount, Decimal):
        amount = float(amount)
    return f"{amount:,.0f}".replace(",", " ")


async def get_user(telegram_id: int) -> User | None:
    async with async_session() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == telegram_id)
        )
        return result.scalar_one_or_none()


def _build_date_picker(year: int, month: int, prefix: str, allow_past: bool = False) -> InlineKeyboardMarkup:
    """Build a calendar for date selection."""
    import calendar

    today = date.today()
    max_date = today + timedelta(days=MAX_FUTURE_DAYS)

    buttons = []

    # Month/year header with nav arrows
    buttons.append([
        InlineKeyboardButton(text="◀️", callback_data=f"{prefix}:prev:{year}:{month}"),
        InlineKeyboardButton(text=f"{MONTH_NAMES_RU[month]} {year}", callback_data=f"{prefix}:noop"),
        InlineKeyboardButton(text="▶️", callback_data=f"{prefix}:next:{year}:{month}"),
    ])

    # Day-of-week header
    buttons.append([
        InlineKeyboardButton(text=d, callback_data=f"{prefix}:noop") for d in DAY_NAMES_RU
    ])

    # Day grid
    cal = calendar.monthcalendar(year, month)
    for week in cal:
        row = []
        for day_num in week:
            if day_num == 0:
                row.append(InlineKeyboardButton(text=" ", callback_data=f"{prefix}:noop"))
            else:
                d = date(year, month, day_num)
                if (not allow_past and d < today) or d > max_date:
                    row.append(InlineKeyboardButton(text="·", callback_data=f"{prefix}:noop"))
                elif d == today:
                    row.append(InlineKeyboardButton(
                        text=f"[{day_num}]",
                        callback_data=f"{prefix}:day:{d.isoformat()}",
                    ))
                else:
                    row.append(InlineKeyboardButton(
                        text=str(day_num),
                        callback_data=f"{prefix}:day:{d.isoformat()}",
                    ))
        buttons.append(row)

    buttons.append([InlineKeyboardButton(text="❌ Отмена", callback_data="prepay:cancel")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


# ── Entry point ───────────────────────────────────────────────────


@router.callback_query(F.data == "action:prepayment")
async def on_prepayment_start(callback: types.CallbackQuery, state: FSMContext):
    """Start prepayment flow — ask for guest name."""
    user = await get_user(callback.from_user.id)
    if not user:
        await callback.answer("Пользователь не найден")
        return

    lang = user.language.value.lower()
    await state.update_data(
        lang=lang,
        user_telegram_id=user.telegram_id,
    )

    await state.set_state(PrepaymentStates.entering_guest_name)
    await callback.message.edit_text(
        "💵 <b>Новая предоплата</b>\n\n"
        "👤 Введите имя гостя:",
    )
    await callback.answer()


# ── Guest name → property picker ─────────────────────────────────


@router.message(PrepaymentStates.entering_guest_name)
async def on_guest_name_entered(message: types.Message, state: FSMContext):
    """Guest name entered — show property list."""
    guest_name = message.text.strip()
    if not guest_name or len(guest_name) < 2:
        await message.answer("❌ Введите корректное имя гостя (минимум 2 символа)")
        return

    await state.update_data(guest_name=guest_name)

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
    await message.answer(
        f"💵 <b>Предоплата</b>\n"
        f"👤 Гость: {guest_name}\n\n"
        f"🏠 Выберите объект:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard_buttons),
    )


# ── Property selected → check-in date ───────────────────────────


@router.callback_query(F.data.startswith("pprop:"), PrepaymentStates.choosing_property)
async def on_property_selected(callback: types.CallbackQuery, state: FSMContext):
    """Property selected — show check-in date picker."""
    prop_id = int(callback.data.split(":")[1])

    async with async_session() as session:
        result = await session.execute(select(Property).where(Property.id == prop_id))
        prop = result.scalar_one_or_none()

    if not prop:
        await callback.answer("Объект не найден")
        return

    await state.update_data(property_id=prop_id, property_name=prop.name_ru)
    data = await state.get_data()

    today = date.today()
    tomorrow = today + timedelta(days=1)

    buttons = [
        [InlineKeyboardButton(
            text=f"📅 Сегодня ({today.strftime('%d.%m')})",
            callback_data=f"pcin:day:{today.isoformat()}",
        )],
        [InlineKeyboardButton(
            text=f"📅 Завтра ({tomorrow.strftime('%d.%m')})",
            callback_data=f"pcin:day:{tomorrow.isoformat()}",
        )],
        [InlineKeyboardButton(
            text="📆 Выбрать дату...",
            callback_data=f"pcin:show:{today.year}:{today.month}",
        )],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="prepay:cancel")],
    ]

    await state.set_state(PrepaymentStates.choosing_checkin_date)
    await callback.message.edit_text(
        f"💵 <b>Предоплата</b>\n"
        f"👤 Гость: {data['guest_name']}\n"
        f"🏠 Объект: {prop.name_ru}\n\n"
        f"📅 Выберите дату заезда:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
    )
    await callback.answer()


# ── Check-in calendar navigation ─────────────────────────────────


@router.callback_query(F.data.startswith("pcin:show:"), PrepaymentStates.choosing_checkin_date)
async def on_checkin_show_cal(callback: types.CallbackQuery, state: FSMContext):
    parts = callback.data.split(":")
    year, month = int(parts[2]), int(parts[3])
    keyboard = _build_date_picker(year, month, "pcin")
    data = await state.get_data()
    await callback.message.edit_text(
        f"💵 <b>Предоплата</b>\n"
        f"👤 {data['guest_name']} | 🏠 {data['property_name']}\n\n"
        f"📅 Выберите дату заезда:",
        reply_markup=keyboard,
    )
    await callback.answer()


@router.callback_query(F.data.startswith("pcin:prev:"), PrepaymentStates.choosing_checkin_date)
async def on_checkin_prev(callback: types.CallbackQuery, state: FSMContext):
    parts = callback.data.split(":")
    year, month = int(parts[2]), int(parts[3])
    month -= 1
    if month < 1:
        month = 12
        year -= 1
    keyboard = _build_date_picker(year, month, "pcin")
    data = await state.get_data()
    await callback.message.edit_text(
        f"💵 <b>Предоплата</b>\n"
        f"👤 {data['guest_name']} | 🏠 {data['property_name']}\n\n"
        f"📅 Выберите дату заезда:",
        reply_markup=keyboard,
    )
    await callback.answer()


@router.callback_query(F.data.startswith("pcin:next:"), PrepaymentStates.choosing_checkin_date)
async def on_checkin_next(callback: types.CallbackQuery, state: FSMContext):
    parts = callback.data.split(":")
    year, month = int(parts[2]), int(parts[3])
    month += 1
    if month > 12:
        month = 1
        year += 1
    keyboard = _build_date_picker(year, month, "pcin")
    data = await state.get_data()
    await callback.message.edit_text(
        f"💵 <b>Предоплата</b>\n"
        f"👤 {data['guest_name']} | 🏠 {data['property_name']}\n\n"
        f"📅 Выберите дату заезда:",
        reply_markup=keyboard,
    )
    await callback.answer()


@router.callback_query(F.data == "pcin:noop", PrepaymentStates.choosing_checkin_date)
async def on_checkin_noop(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()


# ── Check-in date selected → check-out date ─────────────────────


@router.callback_query(F.data.startswith("pcin:day:"), PrepaymentStates.choosing_checkin_date)
async def on_checkin_date_selected(callback: types.CallbackQuery, state: FSMContext):
    """Check-in date selected — show check-out date picker."""
    date_str = callback.data.split(":", 2)[2]
    checkin = date.fromisoformat(date_str)
    await state.update_data(check_in_date=date_str)

    data = await state.get_data()

    # Quick options for checkout
    one_night = checkin + timedelta(days=1)
    two_nights = checkin + timedelta(days=2)
    three_nights = checkin + timedelta(days=3)

    buttons = [
        [InlineKeyboardButton(
            text=f"1 ночь → {one_night.strftime('%d.%m')}",
            callback_data=f"pcout:day:{one_night.isoformat()}",
        )],
        [InlineKeyboardButton(
            text=f"2 ночи → {two_nights.strftime('%d.%m')}",
            callback_data=f"pcout:day:{two_nights.isoformat()}",
        )],
        [InlineKeyboardButton(
            text=f"3 ночи → {three_nights.strftime('%d.%m')}",
            callback_data=f"pcout:day:{three_nights.isoformat()}",
        )],
        [InlineKeyboardButton(
            text="📆 Выбрать дату выезда...",
            callback_data=f"pcout:show:{checkin.year}:{checkin.month}",
        )],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="prepay:cancel")],
    ]

    await state.set_state(PrepaymentStates.choosing_checkout_date)
    await callback.message.edit_text(
        f"💵 <b>Предоплата</b>\n"
        f"👤 {data['guest_name']} | 🏠 {data['property_name']}\n"
        f"📅 Заезд: {checkin.strftime('%d.%m.%Y')}\n\n"
        f"📅 Выберите дату выезда:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
    )
    await callback.answer()


# ── Check-out calendar navigation ────────────────────────────────


@router.callback_query(F.data.startswith("pcout:show:"), PrepaymentStates.choosing_checkout_date)
async def on_checkout_show_cal(callback: types.CallbackQuery, state: FSMContext):
    parts = callback.data.split(":")
    year, month = int(parts[2]), int(parts[3])
    keyboard = _build_date_picker(year, month, "pcout")
    data = await state.get_data()
    checkin = date.fromisoformat(data['check_in_date'])
    await callback.message.edit_text(
        f"💵 <b>Предоплата</b>\n"
        f"👤 {data['guest_name']} | 🏠 {data['property_name']}\n"
        f"📅 Заезд: {checkin.strftime('%d.%m.%Y')}\n\n"
        f"📅 Выберите дату выезда:",
        reply_markup=keyboard,
    )
    await callback.answer()


@router.callback_query(F.data.startswith("pcout:prev:"), PrepaymentStates.choosing_checkout_date)
async def on_checkout_prev(callback: types.CallbackQuery, state: FSMContext):
    parts = callback.data.split(":")
    year, month = int(parts[2]), int(parts[3])
    month -= 1
    if month < 1:
        month = 12
        year -= 1
    keyboard = _build_date_picker(year, month, "pcout")
    data = await state.get_data()
    checkin = date.fromisoformat(data['check_in_date'])
    await callback.message.edit_text(
        f"💵 <b>Предоплата</b>\n"
        f"👤 {data['guest_name']} | 🏠 {data['property_name']}\n"
        f"📅 Заезд: {checkin.strftime('%d.%m.%Y')}\n\n"
        f"📅 Выберите дату выезда:",
        reply_markup=keyboard,
    )
    await callback.answer()


@router.callback_query(F.data.startswith("pcout:next:"), PrepaymentStates.choosing_checkout_date)
async def on_checkout_next(callback: types.CallbackQuery, state: FSMContext):
    parts = callback.data.split(":")
    year, month = int(parts[2]), int(parts[3])
    month += 1
    if month > 12:
        month = 1
        year += 1
    keyboard = _build_date_picker(year, month, "pcout")
    data = await state.get_data()
    checkin = date.fromisoformat(data['check_in_date'])
    await callback.message.edit_text(
        f"💵 <b>Предоплата</b>\n"
        f"👤 {data['guest_name']} | 🏠 {data['property_name']}\n"
        f"📅 Заезд: {checkin.strftime('%d.%m.%Y')}\n\n"
        f"📅 Выберите дату выезда:",
        reply_markup=keyboard,
    )
    await callback.answer()


@router.callback_query(F.data == "pcout:noop", PrepaymentStates.choosing_checkout_date)
async def on_checkout_noop(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()


# ── Check-out date selected → payment method ─────────────────────


@router.callback_query(F.data.startswith("pcout:day:"), PrepaymentStates.choosing_checkout_date)
async def on_checkout_date_selected(callback: types.CallbackQuery, state: FSMContext):
    """Check-out date selected — validate and ask for payment method."""
    date_str = callback.data.split(":", 2)[2]
    checkout = date.fromisoformat(date_str)
    data = await state.get_data()
    checkin = date.fromisoformat(data['check_in_date'])

    if checkout <= checkin:
        await callback.answer("Дата выезда должна быть позже даты заезда!", show_alert=True)
        return

    nights = (checkout - checkin).days
    await state.update_data(check_out_date=date_str, nights=nights)

    # Payment method buttons
    buttons = []
    for pm in PREPAY_METHODS:
        buttons.append([InlineKeyboardButton(
            text=PAYMENT_METHOD_LABELS.get(pm, pm.value),
            callback_data=f"ppm:{pm.value}",
        )])
    buttons.append([InlineKeyboardButton(text="❌ Отмена", callback_data="prepay:cancel")])

    await state.set_state(PrepaymentStates.choosing_payment_method)
    await callback.message.edit_text(
        f"💵 <b>Предоплата</b>\n"
        f"👤 {data['guest_name']} | 🏠 {data['property_name']}\n"
        f"📅 {checkin.strftime('%d.%m')} → {checkout.strftime('%d.%m')} ({nights} {'ночь' if nights == 1 else 'ночей' if nights >= 5 else 'ночи'})\n\n"
        f"💳 Выберите способ оплаты:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
    )
    await callback.answer()


# ── Payment method selected → enter amount ───────────────────────


@router.callback_query(F.data.startswith("ppm:"), PrepaymentStates.choosing_payment_method)
async def on_payment_method_selected(callback: types.CallbackQuery, state: FSMContext):
    """Payment method selected — ask for amount."""
    pm_value = callback.data.split(":")[1]
    pm = PaymentMethod(pm_value)
    pm_label = PAYMENT_METHOD_LABELS.get(pm, pm.value)

    await state.update_data(payment_method=pm_value, payment_method_label=pm_label)
    data = await state.get_data()
    checkin = date.fromisoformat(data['check_in_date'])
    checkout = date.fromisoformat(data['check_out_date'])

    await state.set_state(PrepaymentStates.entering_amount)
    await callback.message.edit_text(
        f"💵 <b>Предоплата</b>\n"
        f"👤 {data['guest_name']} | 🏠 {data['property_name']}\n"
        f"📅 {checkin.strftime('%d.%m')} → {checkout.strftime('%d.%m')} ({data['nights']} н.)\n"
        f"💳 {pm_label}\n\n"
        f"💰 Введите сумму предоплаты:",
    )
    await callback.answer()


# ── Amount entered → upload screenshot ───────────────────────────


@router.message(PrepaymentStates.entering_amount)
async def on_amount_entered(message: types.Message, state: FSMContext):
    """Amount entered — ask for screenshot."""
    raw = message.text.strip().replace(" ", "").replace(",", "").replace(".", "")
    try:
        amount = Decimal(raw)
        if amount <= 0:
            raise ValueError
    except (ValueError, Exception):
        await message.answer("❌ Введите корректную сумму (только цифры)")
        return

    await state.update_data(amount=str(amount))
    data = await state.get_data()
    checkin = date.fromisoformat(data['check_in_date'])
    checkout = date.fromisoformat(data['check_out_date'])

    buttons = [
        [InlineKeyboardButton(text="⏭ Пропустить скриншот", callback_data="prepay:skip_screenshot")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="prepay:cancel")],
    ]

    await state.set_state(PrepaymentStates.uploading_screenshot)
    await message.answer(
        f"💵 <b>Предоплата</b>\n"
        f"👤 {data['guest_name']} | 🏠 {data['property_name']}\n"
        f"📅 {checkin.strftime('%d.%m')} → {checkout.strftime('%d.%m')}\n"
        f"💳 {data['payment_method_label']} | 💰 {format_amount(amount)}\n\n"
        f"📸 Отправьте скриншот подтверждения оплаты\n"
        f"(или нажмите «Пропустить»):",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
    )


# ── Screenshot uploaded → confirmation ───────────────────────────


@router.message(PrepaymentStates.uploading_screenshot, F.photo)
async def on_screenshot_uploaded(message: types.Message, state: FSMContext):
    """Screenshot photo received — show confirmation."""
    # Get the highest resolution photo
    photo = message.photo[-1]
    file_id = photo.file_id
    await state.update_data(screenshot_file_id=file_id)

    await _show_confirmation(message, state, is_edit=False)


@router.callback_query(F.data == "prepay:skip_screenshot", PrepaymentStates.uploading_screenshot)
async def on_skip_screenshot(callback: types.CallbackQuery, state: FSMContext):
    """Skip screenshot — show confirmation."""
    await state.update_data(screenshot_file_id=None)
    await _show_confirmation(callback.message, state, is_edit=True)
    await callback.answer()


async def _show_confirmation(message: types.Message, state: FSMContext, is_edit: bool = False):
    """Show confirmation summary."""
    data = await state.get_data()
    checkin = date.fromisoformat(data['check_in_date'])
    checkout = date.fromisoformat(data['check_out_date'])
    amount = Decimal(data['amount'])
    has_screenshot = bool(data.get('screenshot_file_id'))

    summary = (
        f"💵 <b>Подтверждение предоплаты</b>\n\n"
        f"👤 Гость: <b>{data['guest_name']}</b>\n"
        f"🏠 Объект: <b>{data['property_name']}</b>\n"
        f"📅 Заезд: <b>{checkin.strftime('%d.%m.%Y')}</b>\n"
        f"📅 Выезд: <b>{checkout.strftime('%d.%m.%Y')}</b> ({data['nights']} н.)\n"
        f"💳 Оплата: <b>{data['payment_method_label']}</b>\n"
        f"💰 Сумма: <b>{format_amount(amount)} UZS</b>\n"
        f"📸 Скриншот: {'✅ Загружен' if has_screenshot else '❌ Нет'}\n\n"
        f"Подтвердить?"
    )

    buttons = [
        [
            InlineKeyboardButton(text="✅ Подтвердить", callback_data="prepay:confirm"),
            InlineKeyboardButton(text="❌ Отмена", callback_data="prepay:cancel"),
        ]
    ]

    await state.set_state(PrepaymentStates.confirming)
    if is_edit:
        await message.edit_text(summary, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    else:
        await message.answer(summary, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))


# ── Confirm → save ────────────────────────────────────────────────


@router.callback_query(F.data == "prepay:confirm", PrepaymentStates.confirming)
async def on_prepay_confirm(callback: types.CallbackQuery, state: FSMContext):
    """Save prepayment record."""
    data = await state.get_data()
    checkin = date.fromisoformat(data['check_in_date'])
    checkout = date.fromisoformat(data['check_out_date'])

    async with async_session() as session:
        prepayment = Prepayment(
            guest_name=data['guest_name'],
            property_id=data['property_id'],
            check_in_date=checkin,
            check_out_date=checkout,
            amount=Decimal(data['amount']),
            payment_method=data['payment_method'],
            status=PrepaymentStatus.CONFIRMED,
            screenshot_file_id=data.get('screenshot_file_id'),
            operator_telegram_id=data['user_telegram_id'],
        )
        session.add(prepayment)
        await session.commit()

    # Clear state and return to main menu
    await state.clear()

    user = await get_user(callback.from_user.id)
    lang = user.language.value.lower() if user else "ru"
    section = user.active_section.value.lower() if user else "resort"
    section_name = get_text(f"section_{section}", lang)

    await callback.message.edit_text(
        f"✅ <b>Предоплата сохранена!</b>\n\n"
        f"👤 {data['guest_name']}\n"
        f"🏠 {data['property_name']}\n"
        f"📅 {checkin.strftime('%d.%m')} → {checkout.strftime('%d.%m')}\n"
        f"💰 {format_amount(data['amount'])} UZS\n\n"
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
