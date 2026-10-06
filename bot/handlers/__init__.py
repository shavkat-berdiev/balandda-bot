import logging

from aiogram import Router, types

from bot.handlers.cash_flow import router as cash_flow_router
from bot.handlers.history import router as history_router
from bot.handlers.import_report import router as import_router
from bot.handlers.language import router as language_router
from bot.handlers.new_expense import router as new_expense_router
from bot.handlers.new_report import router as new_report_router
from bot.handlers.prepayment import router as prepayment_router
from bot.handlers.purchase import router as purchase_router
from bot.handlers.report import router as report_router
from bot.handlers.reporting_group import router as reporting_group_router
from bot.handlers.start import router as start_router
from bot.handlers.wallet import router as wallet_router
from bot.handlers.xush import router as xush_router
from bot.iiko_wallet_sync import router as iiko_sync_router
from bot.owner_digest import router as owner_digest_router

logger = logging.getLogger(__name__)

# Debug catch-all — must be its own router, included LAST
debug_router = Router()


STALE_SESSION_TEXT = (
    "⚠️ Сессия сброшена — начните заново: /start\n"
    "⚠️ Sessiya yangilandi — qaytadan boshlang: /start"
)
STALE_BUTTON_ALERT = (
    "⚠️ Эта кнопка устарела. Нажмите /start и начните заново.\n\n"
    "⚠️ Bu tugma eskirgan. /start ni bosib, qaytadan boshlang."
)


@debug_router.message()
async def debug_catch_all(message: types.Message):
    logger.warning(
        f"UNHANDLED message from user={message.from_user.id}, "
        f"content_type={message.content_type}, "
        f"text={message.text[:80] if message.text else 'None'}"
    )
    # Never leave a private-chat user talking to silence
    if message.chat.type == "private":
        try:
            await message.answer(STALE_SESSION_TEXT)
        except Exception:
            pass


@debug_router.callback_query()
async def stale_callback(callback: types.CallbackQuery):
    """A button no handler accepted (old card, or flow state lost) - say so instead of spinning."""
    data = callback.data or ""
    if data.endswith(":noop"):
        await callback.answer()  # calendar headers / blanks
        return
    logger.warning(f"UNHANDLED callback from user={callback.from_user.id}, data={data[:64]}")
    try:
        await callback.answer(STALE_BUTTON_ALERT, show_alert=True)
    except Exception:
        pass


# Import order matters — more specific routers first
main_router = Router()
main_router.include_router(reporting_group_router)  # Reporting group topics (/bind /routes /unbind) + swallows all other group traffic — MUST be first
main_router.include_router(start_router)
main_router.include_router(new_report_router)   # Structured report flow
main_router.include_router(new_expense_router)   # Expense entry flow
main_router.include_router(prepayment_router)    # Quick prepayment flow
main_router.include_router(purchase_router)      # Purchase report flow
main_router.include_router(xush_router)           # XUSH simplified cash-box flow
main_router.include_router(wallet_router)        # Wallet / cash transfers
main_router.include_router(cash_flow_router)
main_router.include_router(history_router)
main_router.include_router(report_router)
main_router.include_router(import_router)
main_router.include_router(language_router)
main_router.include_router(owner_digest_router)  # /svodka — owner on-demand digest
main_router.include_router(iiko_sync_router)     # /iiko_sync — iiko cash → wallet
main_router.include_router(debug_router)  # Must be last
