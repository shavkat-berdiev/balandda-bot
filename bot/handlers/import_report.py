"""Handler for importing daily reports via forwarded messages.

Admin forwards a daily report text message to the bot.
The bot parses it, shows a preview, and asks for confirmation before saving.
"""

import logging
from datetime import date

from aiogram import F, Router, types
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import select

from bot.config import settings
from bot.parser import parse_daily_report, format_parsed_report, ParsedReport
from db.database import async_session
from db.models import (
    BusinessUnit,
    DailyReport,
    ReportExpense,
    ReportLineItem,
    User,
    UserRole,
)

router = Router()
logger = logging.getLogger(__name__)


class ImportStates(StatesGroup):
    waiting_for_confirm = State()


async def is_admin(telegram_id: int) -> bool:
    """Check if the user is an admin."""
    async with async_session() as session:
        result = await session.execute(
            select(User).where(
                User.telegram_id == telegram_id,
                User.role == UserRole.ADMIN,
                User.is_active == True,
            )
        )
        return result.scalar_one_or_none() is not None


def _build_confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Сохранить", callback_data="import:confirm"),
            InlineKeyboardButton(text="❌ Отменить", callback_data="import:cancel"),
        ]
    ])


@router.message(F.text & ~F.text.startswith("/"))
async def on_text_message(message: types.Message, state: FSMContext):
    """Handle incoming text messages — try to parse as a daily report.

    Only processes messages from admin users.
    Skips messages that don't look like reports (no date on first line).
    """
    # Only admin can import
    if not await is_admin(message.from_user.id):
        return  # Not admin — let other handlers process this

    # Check if this looks like a report (starts with a date)
    text = message.text.strip()
    first_line = text.split("\n")[0].strip()

    import re
    if not re.match(r"\d{1,2}[./]\d{1,2}[./]\d{2,4}", first_line):
        return  # Doesn't start with a date — not a report, skip

    # Try to parse the report
    report = parse_daily_report(text)
    if report is None:
        await message.answer(
            "❌ Не удалось распознать отчёт. Проверьте формат:\n"
            "Первая строка — дата (ДД.ММ.ГГГГ), далее юниты и оплаты."
        )
        return

    if not report.units and not report.expenses:
        await message.answer("❌ Отчёт пуст — не найдено ни доходов, ни расходов.")
        return

    # Check if report for this date already exists
    async with async_session() as session:
        existing = await session.execute(
            select(DailyReport).where(
                DailyReport.report_date == report.report_date,
                DailyReport.business_unit == BusinessUnit.RESORT,
            )
        )
        if existing.scalar_one_or_none():
            await message.answer(
                f"⚠️ Отчёт за {report.report_date.strftime('%d.%m.%Y')} уже существует.\n"
                "Для перезаписи сначала удалите старый отчёт."
            )
            return

    # Show parsed report for confirmation
    preview = format_parsed_report(report)

    # Telegram message limit is 4096 chars, split if needed
    if len(preview) > 4000:
        parts = [preview[i:i+4000] for i in range(0, len(preview), 4000)]
        for part in parts[:-1]:
            await message.answer(part, parse_mode="HTML")
        await message.answer(
            parts[-1] + "\n\n💾 Сохранить этот отчёт?",
            parse_mode="HTML",
            reply_markup=_build_confirm_keyboard(),
        )
    else:
        await message.answer(
            preview + "\n\n💾 Сохранить этот отчёт?",
            parse_mode="HTML",
            reply_markup=_build_confirm_keyboard(),
        )

    # Store parsed data in FSM for confirmation
    await state.set_state(ImportStates.waiting_for_confirm)
    await state.update_data(
        raw_text=text,
        report_date=report.report_date.isoformat(),
    )


@router.callback_query(F.data == "import:confirm", ImportStates.waiting_for_confirm)
async def on_import_confirm(callback: types.CallbackQuery, state: FSMContext):
    """Save the parsed report to database."""
    data = await state.get_data()
    raw_text = data["raw_text"]
    await state.clear()

    # Re-parse (we don't store the full parsed object in FSM)
    report = parse_daily_report(raw_text)
    if report is None:
        await callback.message.edit_text("❌ Ошибка при повторном разборе отчёта.")
        await callback.answer()
        return

    # Save to database
    try:
        async with async_session() as session:
            db_report = DailyReport(
                report_date=report.report_date,
                business_unit=BusinessUnit.RESORT,
                raw_text=raw_text,
                total_income=report.calculated_income,
                total_expense=report.calculated_expenses,
                balance=report.reported_balance or 0,
                previous_balance=report.reported_yesterday_sum or 0,
                imported_by=callback.from_user.id,
            )
            session.add(db_report)
            await session.flush()  # Get the report ID

            # Save line items
            for unit in report.units:
                for payment in unit.payments:
                    item = ReportLineItem(
                        report_id=db_report.id,
                        accommodation_type=unit.accommodation_type,
                        unit_number=unit.unit_number,
                        unit_label=unit.unit_label,
                        service_description=unit.service_description,
                        payment_method=payment.payment_method,
                        amount=payment.amount,
                        discount_percent=unit.discount_percent,
                        discount_reason=unit.discount_reason,
                        note=unit.note,
                    )
                    session.add(item)

            # Save expenses
            for expense in report.expenses:
                exp = ReportExpense(
                    report_id=db_report.id,
                    expense_category=expense.expense_category,
                    description=expense.description,
                    amount=expense.amount,
                )
                session.add(exp)

            await session.commit()

        units_count = len(report.units)
        payments_count = sum(len(u.payments) for u in report.units)
        expenses_count = len(report.expenses)

        from bot.parser import format_amount
        await callback.message.edit_text(
            f"✅ Отчёт за <b>{report.report_date.strftime('%d.%m.%Y')}</b> сохранён!\n\n"
            f"📊 {units_count} юнитов, {payments_count} платежей, {expenses_count} расходов\n"
            f"💰 Доход: {format_amount(report.calculated_income)}\n"
            f"💸 Расход: {format_amount(report.calculated_expenses)}\n"
            f"📈 Чистый итог: {format_amount(report.calculated_income - report.calculated_expenses)}",
            parse_mode="HTML",
        )
    except Exception as e:
        logger.error(f"Error saving report: {e}", exc_info=True)
        await callback.message.edit_text(f"❌ Ошибка при сохранении: {e}")

    await callback.answer()


@router.callback_query(F.data == "import:cancel", ImportStates.waiting_for_confirm)
async def on_import_cancel(callback: types.CallbackQuery, state: FSMContext):
    """Cancel import."""
    await state.clear()
    await callback.message.edit_text("🚫 Импорт отменён.")
    await callback.answer()
