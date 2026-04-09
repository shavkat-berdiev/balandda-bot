"""Report handler — daily summary with date selection for current section."""

import logging
from datetime import date, timedelta

from aiogram import F, Router, types
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from bot.keyboards.main import main_menu_keyboard
from bot.locales import get_text
from db.database import async_session
from db.enums import EXPENSE_CATEGORY_LABELS, PAYMENT_METHOD_LABELS, UserRole
from db.models import (
    ExpenseEntry,
    IncomeEntry,
    StructuredReport,
    User,
)

router = Router()
logger = logging.getLogger(__name__)


class ReportStates(StatesGroup):
    viewing = State()


def format_amount(amount: float) -> str:
    """Format amount with dot separators (e.g., 3.200.000)."""
    return f"{amount:,.0f}".replace(",", ".")


async def build_daily_report(business_unit, target_date: date, lang: str, detailed: bool = False) -> str:
    """Build daily report from structured reports (both draft and submitted).

    detailed=True adds breakdown by payment method (for admins).
    """
    async with async_session() as session:
        result = await session.execute(
            select(StructuredReport)
            .where(
                StructuredReport.report_date == target_date,
                StructuredReport.business_unit == business_unit,
            )
            .options(
                selectinload(StructuredReport.income_entries).selectinload(IncomeEntry.property),
                selectinload(StructuredReport.income_entries).selectinload(IncomeEntry.service_item),
                selectinload(StructuredReport.income_entries).selectinload(IncomeEntry.minibar_item),
                selectinload(StructuredReport.expense_entries),
            )
        )
        reports = result.scalars().all()

    total_income = sum(float(r.total_income or 0) for r in reports)
    total_expense = sum(float(r.total_expense or 0) for r in reports)
    net = total_income - total_expense

    date_str = target_date.strftime("%d.%m.%Y")
    section_name = get_text(f"section_{business_unit.value}", lang)
    lines = [
        f"📊 {get_text('report_today', lang, section=section_name)}",
        f"📅 {date_str}",
        "",
        get_text("report_total_in", lang, amount=total_income),
        get_text("report_total_out", lang, amount=total_expense),
        f"{'📈' if net >= 0 else '📉'} {get_text('report_net', lang, amount=net)}",
    ]

    # Group income entries
    property_totals: dict[str, float] = {}
    service_totals: dict[str, float] = {}
    minibar_total = 0.0
    other_income = 0.0
    payment_totals: dict[str, float] = {}

    for report in reports:
        for entry in report.income_entries:
            if entry.property:
                name = entry.property.name_ru
                property_totals[name] = property_totals.get(name, 0) + float(entry.amount)
            elif entry.service_item:
                name = entry.service_item.name_ru
                service_totals[name] = service_totals.get(name, 0) + float(entry.amount)
            elif entry.minibar_item:
                minibar_total += float(entry.amount)
            else:
                other_income += float(entry.amount)

            if detailed:
                pm_label = PAYMENT_METHOD_LABELS.get(entry.payment_method, str(entry.payment_method))
                payment_totals[pm_label] = payment_totals.get(pm_label, 0) + float(entry.amount)

    if property_totals:
        lines.append("")
        lines.append("🏠 Проживание:")
        for name, total in sorted(property_totals.items()):
            lines.append(f"  • {name}: {format_amount(total)} UZS")

    if service_totals:
        lines.append("")
        lines.append("💆 Услуги:")
        for name, total in sorted(service_totals.items()):
            lines.append(f"  • {name}: {format_amount(total)} UZS")

    if minibar_total > 0:
        lines.append(f"\n🍹 Мини-бар: {format_amount(minibar_total)} UZS")

    if other_income > 0:
        lines.append(f"\n💰 Прочий доход: {format_amount(other_income)} UZS")

    # Expense breakdown
    expense_totals: dict[str, float] = {}
    for report in reports:
        for entry in report.expense_entries:
            label = EXPENSE_CATEGORY_LABELS.get(entry.expense_category, str(entry.expense_category))
            expense_totals[label] = expense_totals.get(label, 0) + float(entry.amount)

    if expense_totals:
        lines.append("")
        lines.append("💸 Расходы:")
        for label, total in sorted(expense_totals.items(), key=lambda x: x[1], reverse=True):
            lines.append(f"  • {label}: {format_amount(total)} UZS")

    # Detailed: payment method breakdown (admin only)
    if detailed and payment_totals:
        lines.append("")
        lines.append("💳 По способу оплаты:")
        for label, total in sorted(payment_totals.items(), key=lambda x: x[1], reverse=True):
            lines.append(f"  • {label}: {format_amount(total)} UZS")

    if not reports:
        lines.append("")
        lines.append(get_text("history_empty", lang))
    else:
        lines.append(f"\n📝 Отчётов: {len(reports)}")

    return "\n".join(lines)


def _report_date_keyboard(lang: str) -> InlineKeyboardMarkup:
    """Date selection for report viewing."""
    today = date.today()
    yesterday = today - timedelta(days=1)
    day_before = today - timedelta(days=2)

    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text=f"📅 Сегодня ({today.strftime('%d.%m')})",
                callback_data=f"rptdate:{today.isoformat()}",
            ),
        ],
        [
            InlineKeyboardButton(
                text=f"📅 Вчера ({yesterday.strftime('%d.%m')})",
                callback_data=f"rptdate:{yesterday.isoformat()}",
            ),
        ],
        [
            InlineKeyboardButton(
                text=f"📅 {day_before.strftime('%d.%m')}",
                callback_data=f"rptdate:{day_before.isoformat()}",
            ),
            InlineKeyboardButton(
                text=f"📅 {(today - timedelta(days=3)).strftime('%d.%m')}",
                callback_data=f"rptdate:{(today - timedelta(days=3)).isoformat()}",
            ),
        ],
        [
            InlineKeyboardButton(
                text=f"📅 {(today - timedelta(days=4)).strftime('%d.%m')}",
                callback_data=f"rptdate:{(today - timedelta(days=4)).isoformat()}",
            ),
            InlineKeyboardButton(
                text=f"📅 {(today - timedelta(days=5)).strftime('%d.%m')}",
                callback_data=f"rptdate:{(today - timedelta(days=5)).isoformat()}",
            ),
            InlineKeyboardButton(
                text=f"📅 {(today - timedelta(days=6)).strftime('%d.%m')}",
                callback_data=f"rptdate:{(today - timedelta(days=6)).isoformat()}",
            ),
        ],
        [
            InlineKeyboardButton(
                text=f"◀️ {get_text('btn_back', lang)}",
                callback_data="action:back_menu",
            ),
        ],
    ])


@router.callback_query(F.data == "action:report")
async def on_report(callback: types.CallbackQuery, state: FSMContext):
    """Show date selection for report."""
    async with async_session() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == callback.from_user.id)
        )
        user = result.scalar_one_or_none()

    if not user:
        await callback.answer()
        return

    lang = user.language.value.lower()
    await state.set_state(ReportStates.viewing)

    await callback.message.edit_text(
        "📊 <b>Выберите дату отчёта:</b>",
        reply_markup=_report_date_keyboard(lang),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("rptdate:"), ReportStates.viewing)
async def on_report_date_selected(callback: types.CallbackQuery, state: FSMContext):
    """Show report for selected date."""
    target_date = date.fromisoformat(callback.data.split(":")[1])

    async with async_session() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == callback.from_user.id)
        )
        user = result.scalar_one_or_none()

    if not user:
        await callback.answer()
        return

    lang = user.language.value.lower()
    is_admin = user.role == UserRole.ADMIN
    report_text = await build_daily_report(user.active_section, target_date, lang, detailed=is_admin)

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📅 Другая дата", callback_data="action:report"),
            InlineKeyboardButton(
                text=f"◀️ {get_text('btn_back', lang)}",
                callback_data="action:back_menu",
            ),
        ],
    ])

    await state.clear()
    await callback.message.edit_text(report_text, reply_markup=kb)
    await callback.answer()


# --- Back to menu handler ---

@router.callback_query(F.data == "action:back_menu")
async def on_back_menu(callback: types.CallbackQuery, state: FSMContext):
    """Return to main menu."""
    await state.clear()

    async with async_session() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == callback.from_user.id)
        )
        user = result.scalar_one_or_none()

    if not user:
        await callback.answer()
        return

    lang = user.language.value.lower()
    section = user.active_section.value.lower()
    section_name = get_text(f"section_{section}", lang)

    await callback.message.edit_text(
        get_text("main_menu", lang, section=section_name),
        reply_markup=main_menu_keyboard(lang, current_section=section, role=user.role.value),
    )
    await callback.answer()
