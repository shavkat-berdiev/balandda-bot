"""Daily auto-report sender — sends summary at 21:00 Tashkent time."""

import logging
from datetime import date, datetime, timedelta, timezone

from aiogram import Bot
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from bot import iiko_wallet_sync, owner_digest
from bot.config import settings
from db.database import async_session
from services import beds24
from db.enums import (
    EXPENSE_CATEGORY_LABELS,
    PAYMENT_METHOD_LABELS,
    ReportStatus,
    ReservationStatus,
)
from db.models import (
    ExpenseEntry,
    IncomeEntry,
    MinibarItem,
    Property,
    Reservation,
    ReservationEvent,
    ServiceItem,
    StructuredReport,
    User,
    UserRole,
)

logger = logging.getLogger(__name__)


def format_amount(amount: float) -> str:
    """Format amount with dot separators (e.g., 3.200.000)."""
    return f"{amount:,.0f}".replace(",", ".")


async def build_daily_summary(target_date: date) -> str:
    """Build a daily summary from all structured reports for the date."""
    async with async_session() as session:
        result = await session.execute(
            select(StructuredReport)
            .where(
                StructuredReport.report_date == target_date,
                StructuredReport.status != ReportStatus.DRAFT,
            )
            .options(
                selectinload(StructuredReport.income_entries).selectinload(IncomeEntry.property),
                selectinload(StructuredReport.income_entries).selectinload(IncomeEntry.service_item),
                selectinload(StructuredReport.income_entries).selectinload(IncomeEntry.minibar_item),
                selectinload(StructuredReport.expense_entries),
            )
        )
        reports = result.scalars().all()

    if not reports:
        return f"📊 Отчёт за {target_date.strftime('%d.%m.%Y')}\n\nНет отправленных отчётов за сегодня."

    total_income = sum(float(r.total_income or 0) for r in reports)
    total_expense = sum(float(r.total_expense or 0) for r in reports)
    net = total_income - total_expense

    lines = [
        f"📊 Ежедневный отчёт — {target_date.strftime('%d.%m.%Y')}",
        "",
        f"💰 Доход: {format_amount(total_income)} UZS",
        f"💸 Расход: {format_amount(total_expense)} UZS",
        f"{'📈' if net >= 0 else '📉'} Чистый доход: {format_amount(net)} UZS",
        "",
    ]

    # Group income by property
    property_totals: dict[str, float] = {}
    service_totals: dict[str, float] = {}
    minibar_total = 0.0

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

    if property_totals:
        lines.append("🏠 Проживание:")
        for name, total in sorted(property_totals.items()):
            lines.append(f"  • {name}: {format_amount(total)}")

    if service_totals:
        lines.append("\n💆 Услуги:")
        for name, total in sorted(service_totals.items()):
            lines.append(f"  • {name}: {format_amount(total)}")

    if minibar_total > 0:
        lines.append(f"\n🍹 Мини-бар: {format_amount(minibar_total)}")

    # Expense breakdown
    expense_totals: dict[str, float] = {}
    for report in reports:
        for entry in report.expense_entries:
            label = EXPENSE_CATEGORY_LABELS.get(entry.expense_category, entry.expense_category.value)
            expense_totals[label] = expense_totals.get(label, 0) + float(entry.amount)

    if expense_totals:
        lines.append("\n💸 Расходы:")
        for label, total in sorted(expense_totals.items(), key=lambda x: x[1], reverse=True):
            lines.append(f"  • {label}: {format_amount(total)}")

    lines.append(f"\n📝 Отчётов: {len(reports)}")

    return "\n".join(lines)


async def send_daily_report(bot: Bot):
    """Send the daily summary — to the Reporting group topic if bound, else to admins."""
    from bot.notifications import CAT_REPORTS, send_via_route

    today = date.today()
    logger.info(f"Sending daily report for {today}")

    try:
        summary = await build_daily_summary(today)

        # If the REPORTS category is bound to a group topic, one post there is enough
        if await send_via_route(bot, CAT_REPORTS, summary):
            logger.info("Daily report sent to the Reporting group topic")
            return

        # Fallback — find admins to notify in DMs
        async with async_session() as session:
            result = await session.execute(
                select(User).where(
                    User.role == UserRole.ADMIN,
                    User.is_active == True,
                )
            )
            admins = result.scalars().all()

        if not admins:
            logger.warning("No active admins found to send daily report")
            return

        for admin in admins:
            try:
                await bot.send_message(admin.telegram_id, summary)
                logger.info(f"Daily report sent to admin {admin.full_name} ({admin.telegram_id})")
            except Exception as e:
                logger.error(f"Failed to send daily report to {admin.telegram_id}: {e}")

    except Exception as e:
        logger.error(f"Error building daily report: {e}", exc_info=True)


async def send_balance_reminders(bot: Bot):
    """At 21:00 remind each admin/owner who is holding cash about their balance."""
    from bot.handlers.wallet import get_wallet_balance

    async with async_session() as session:
        result = await session.execute(
            select(User).where(
                User.role.in_([UserRole.ADMIN, UserRole.OWNER]),
                User.is_active == True,
            )
        )
        users = result.scalars().all()

    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="💰 Открыть кошелёк", callback_data="action:wallet"),
    ]])
    for u in users:
        try:
            bal = await get_wallet_balance(u.telegram_id)
            if float(bal) == 0:
                continue  # nothing on hand — don't ping
            await bot.send_message(
                u.telegram_id,
                f"💰 <b>Остаток наличных на конец дня</b>\n\n"
                f"Ваш баланс: <b>{format_amount(float(bal))} UZS</b>\n\n"
                f"Не забудьте сдать инкассацию.",
                reply_markup=kb,
            )
        except Exception as e:
            logger.error(f"Balance reminder failed for {u.telegram_id}: {e}")


# ────────────────────────────────────────────────────────────────────────
# UNACCEPTED TRANSFERS DIGEST  (added 2026-08)
# ────────────────────────────────────────────────────────────────────────

# A transfer sits PENDING until the receiver taps ✅. PENDING deducts from the
# sender and credits nobody, so the cash is frozen — invisible on both balances
# and easy to forget. Azizov quietly accumulated 38 of them (357.6M UZS over four
# months) before anyone noticed, which is what this digest exists to prevent.
#
# Only transfers older than STALE_AFTER_DAYS are listed, so a normal same-day
# hand-off never shows up as a problem.
STALE_AFTER_DAYS = 2


async def build_pending_transfers_digest() -> str | None:
    """Employee transfers still unaccepted after STALE_AFTER_DAYS.

    Returns None when there is nothing to report — the caller stays silent
    rather than posting "all clear" into the group every night.
    """
    from db.enums import WalletTransactionStatus, WalletTransactionType
    from db.models import WalletTransaction

    cutoff = datetime.now(timezone.utc) - timedelta(days=STALE_AFTER_DAYS)

    async with async_session() as session:
        rows = (await session.execute(
            select(WalletTransaction)
            .where(
                WalletTransaction.status == WalletTransactionStatus.PENDING,
                WalletTransaction.transaction_type.in_([
                    WalletTransactionType.TRANSFER_TO_EMPLOYEE,
                    WalletTransactionType.TRANSFER_TO_SHAVKAT,
                ]),
                WalletTransaction.created_at < cutoff,
            )
            .order_by(WalletTransaction.created_at)
        )).scalars().all()

        if not rows:
            return None

        ids = {t.receiver_telegram_id for t in rows} | {t.sender_telegram_id for t in rows}
        ids.discard(None)
        names = {
            u.telegram_id: u.full_name
            for u in (await session.execute(
                select(User).where(User.telegram_id.in_(ids))
            )).scalars().all()
        }

    by_receiver: dict[int, list] = {}
    for t in rows:
        by_receiver.setdefault(t.receiver_telegram_id, []).append(t)

    today = date.today()
    grand = sum(float(t.amount) for t in rows)

    lines = [
        "⏳ <b>Непринятые переводы</b>",
        f"Не подтверждены дольше {STALE_AFTER_DAYS} дн. — деньги «заморожены»: "
        f"списаны у отправителя, никому не зачислены.",
        "",
    ]

    # Worst offender first
    for rid, txs in sorted(by_receiver.items(), key=lambda kv: -sum(float(t.amount) for t in kv[1])):
        total = sum(float(t.amount) for t in txs)
        oldest = min((t.created_at.date() for t in txs if t.created_at), default=None)
        age = f", самый старый {(today - oldest).days} дн." if oldest else ""
        lines.append(f"👤 <b>{names.get(rid, '?')}</b> — {len(txs)} шт. на "
                     f"<b>{format_amount(total)}</b> UZS{age}")

        # Newest few per person; the rest are rolled up so the message stays readable
        for t in sorted(txs, key=lambda x: x.created_at or datetime.min.replace(tzinfo=timezone.utc),
                        reverse=True)[:5]:
            d = t.created_at.strftime("%d.%m") if t.created_at else "—"
            days = (today - t.created_at.date()).days if t.created_at else 0
            lines.append(f"   · {d} от {names.get(t.sender_telegram_id, '?')} — "
                         f"{format_amount(float(t.amount))} ({days} дн.)")
        if len(txs) > 5:
            rest = sum(float(t.amount) for t in sorted(
                txs, key=lambda x: x.created_at or datetime.min.replace(tzinfo=timezone.utc),
                reverse=True)[5:])
            lines.append(f"   · … и ещё {len(txs) - 5} на {format_amount(rest)}")
        lines.append("")

    lines.append(f"💰 <b>Итого заморожено: {format_amount(grand)} UZS</b>")
    lines.append("")
    lines.append("Получателю: «Кошелёк» → «📥 Входящие» — принять или отклонить.")
    return "\n".join(lines)


async def send_pending_transfers_digest(bot: Bot):
    """Post the digest into the Инкассация topic of the reporting group."""
    from bot.notifications import CAT_INKASSATSIYA, notify_owners, send_via_route

    try:
        text = await build_pending_transfers_digest()
        if text is None:
            logger.info("No stale pending transfers — digest skipped")
            return

        if await send_via_route(bot, CAT_INKASSATSIYA, text):
            logger.info("Pending-transfers digest sent to the Инкассация topic")
            return

        # Not bound to a topic yet — fall back to owner DMs so it is never lost.
        logger.warning("CAT_INKASSATSIYA not bound to a topic; sending digest to owners")
        notify_owners(bot, text, category=None)
    except Exception as e:
        logger.error(f"Pending-transfers digest failed: {e}", exc_info=True)


async def _safe_send(bot: Bot, chat_id: int, text: str) -> None:
    try:
        await bot.send_message(chat_id, text)
    except Exception as e:
        logger.warning(f"Hold notification to {chat_id} failed: {e}")


async def process_hold_expiries(bot: Bot):
    """Warn and expire unpaid booking holds.

    Timers (warn +30m, expire +60m of working time) were computed at booking creation,
    so we only compare against them here. Runs every few minutes. First payment already
    cleared the timers, so only still-unpaid HOLDs are ever touched.
    """
    now = datetime.now(timezone.utc)
    expired_any = False
    async with async_session() as session:
        holds = (
            await session.execute(
                select(Reservation).where(
                    Reservation.status == ReservationStatus.HOLD,
                    Reservation.hold_expires_at.is_not(None),
                )
            )
        ).scalars().all()

        for res in holds:
            prop = await session.get(Property, res.property_id)
            unit = prop.name_ru if prop else str(res.property_id)
            who = res.guest_name or (f"@{res.telegram_username}" if res.telegram_username else "гость")
            dates = f"{res.check_in.strftime('%d.%m')}–{res.check_out.strftime('%d.%m')}"
            label = f"{unit} · {who} · {dates}"

            # Expire (checked first, in case the scheduler was paused past both points)
            if res.hold_expires_at and now >= res.hold_expires_at:
                res.status = ReservationStatus.EXPIRED
                expired_any = True
                session.add(ReservationEvent(
                    reservation_id=res.id, actor_name="Авто (таймер)", action="auto",
                    detail="Бронь истекла: предоплата не внесена вовремя. Дата освобождена.",
                ))
                await session.commit()
                if res.created_by:
                    await _safe_send(bot, res.created_by, f"⌛️ Бронь истекла (не оплачена): {label}. Дата освобождена.")
                if res.telegram_user_id:
                    await _safe_send(bot, res.telegram_user_id,
                                     f"К сожалению, ваша бронь ({unit}, {dates}) отменена — предоплата не поступила вовремя.")
                continue

            # Warn once
            if res.hold_warn_at and now >= res.hold_warn_at and res.hold_warned_at is None:
                res.hold_warned_at = now
                await session.commit()
                if res.created_by:
                    tg = f" (@{res.telegram_username})" if res.telegram_username else ""
                    await _safe_send(bot, res.created_by,
                                     f"⚠️ Бронь без предоплаты: {label}{tg}. Свяжитесь с клиентом — через 30 минут авто-отмена.")
                if res.telegram_user_id:
                    await _safe_send(bot, res.telegram_user_id,
                                     f"⚠️ Ваша бронь ({unit}, {dates}) ещё не оплачена. Пожалуйста, внесите предоплату в течение 30 минут, иначе бронь будет отменена.")

    if expired_any:
        beds24.kick()  # expired holds freed dates → update the OTA channels


def setup_scheduler(bot: Bot) -> AsyncIOScheduler:
    """Set up and return the APScheduler instance."""
    scheduler = AsyncIOScheduler(timezone=settings.timezone)

    scheduler.add_job(
        process_hold_expiries,
        IntervalTrigger(minutes=5),
        args=[bot],
        id="hold_expiries",
        name="Booking hold expiries",
        replace_existing=True,
    )

    scheduler.add_job(
        send_daily_report,
        CronTrigger(
            hour=settings.daily_report_hour,
            minute=settings.daily_report_minute,
            timezone=settings.timezone,
        ),
        args=[bot],
        id="daily_report",
        name="Daily Report",
        replace_existing=True,
    )

    scheduler.add_job(
        send_balance_reminders,
        CronTrigger(
            hour=settings.daily_report_hour,
            minute=settings.daily_report_minute,
            timezone=settings.timezone,
        ),
        args=[bot],
        id="balance_reminders",
        name="Balance Reminders",
        replace_existing=True,
    )

    # Frozen cash: transfers nobody accepted. A few minutes after the daily report
    # so the two posts don't race each other into the group.
    scheduler.add_job(
        send_pending_transfers_digest,
        CronTrigger(
            hour=settings.daily_report_hour,
            minute=(settings.daily_report_minute + 5) % 60,
            timezone=settings.timezone,
        ),
        args=[bot],
        id="pending_transfers_digest",
        name="Unaccepted transfers digest",
        replace_existing=True,
    )

    # Owner digests: bookings + money-in + wallets (OWNER users only)
    scheduler.add_job(
        owner_digest.send_morning_digest,
        CronTrigger(
            hour=settings.owner_digest_morning_hour,
            minute=settings.owner_digest_morning_minute,
            timezone=settings.timezone,
        ),
        args=[bot],
        id="owner_morning_digest",
        name="Owner Morning Digest",
        replace_existing=True,
    )
    scheduler.add_job(
        owner_digest.send_evening_digest,
        CronTrigger(
            hour=settings.daily_report_hour,
            minute=settings.daily_report_minute,
            timezone=settings.timezone,
        ),
        args=[bot],
        id="owner_evening_digest",
        name="Owner Evening Digest",
        replace_existing=True,
    )

    # iiko cash → restaurant manager wallet (23:30 today; 08:50 late-cheque top-up)
    scheduler.add_job(
        iiko_wallet_sync.sync_today,
        CronTrigger(hour=23, minute=30, timezone=settings.timezone),
        args=[bot],
        id="iiko_cash_sync_evening",
        name="iiko cash → wallet (today)",
        replace_existing=True,
    )
    scheduler.add_job(
        iiko_wallet_sync.sync_yesterday,
        CronTrigger(hour=8, minute=50, timezone=settings.timezone),
        args=[bot],
        id="iiko_cash_sync_morning",
        name="iiko cash → wallet (late cheques)",
        replace_existing=True,
    )

    # Card monitoring: periodic matching + evening reconciliation posts
    from bot import card_matcher, card_recon

    scheduler.add_job(
        card_matcher.run_matching,
        IntervalTrigger(minutes=30),
        id="card_matching",
        name="Card transfer matching",
        replace_existing=True,
    )
    scheduler.add_job(
        card_recon.send_daily_reconciliation,
        CronTrigger(
            hour=settings.card_recon_hour,
            minute=settings.card_recon_minute,
            timezone=settings.timezone,
        ),
        args=[bot],
        id="card_reconciliation",
        name="Daily card reconciliation",
        replace_existing=True,
    )

    # SPA bot: morning schedule digest to masters + SPA admin + owners
    # (no-op unless SPA_BOT_TOKEN is set)
    from services import spa_notify

    scheduler.add_job(
        spa_notify.send_daily_digest,
        CronTrigger(
            hour=settings.spa_digest_hour,
            minute=settings.spa_digest_minute,
            timezone=settings.timezone,
        ),
        id="spa_daily_digest",
        name="SPA: daily schedule digest",
        replace_existing=True,
    )

    # Beds24 channel-manager sync (no-ops unless BEDS24_ENABLED)
    scheduler.add_job(
        beds24.pull_bookings,
        IntervalTrigger(minutes=5),
        id="beds24_pull",
        name="Beds24: import OTA bookings",
        replace_existing=True,
    )
    scheduler.add_job(
        beds24.push_full,
        IntervalTrigger(minutes=60),
        id="beds24_push",
        name="Beds24: full availability/price push",
        replace_existing=True,
    )

    logger.info(
        f"Scheduler configured: daily report at "
        f"{settings.daily_report_hour:02d}:{settings.daily_report_minute:02d} "
        f"{settings.timezone}"
    )

    return scheduler
