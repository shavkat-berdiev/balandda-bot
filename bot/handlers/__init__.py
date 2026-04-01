import logging

from aiogram import Router, types

from bot.handlers.cash_flow import router as cash_flow_router
from bot.handlers.history import router as history_router
from bot.handlers.import_report import router as import_router
from bot.handlers.language import router as language_router
from bot.handlers.new_expense import router as new_expense_router
from bot.handlers.new_report import router as new_report_router
from bot.handlers.report import router as report_router
from bot.handlers.start import router as start_router

logger = logging.getLogger(__name__)

# Debug catch-all — must be its own router, included LAST
debug_router = Router()


@debug_router.message()
async def debug_catch_all(message: types.Message):
    logger.warning(
        f"UNHANDLED message from user={message.from_user.id}, "
        f"content_type={message.content_type}, "
        f"text={message.text[:80] if message.text else 'None'}"
    )


# Import order matters — more specific routers first
main_router = Router()
main_router.include_router(start_router)
main_router.include_router(new_report_router)   # Structured report flow
main_router.include_router(new_expense_router)   # Expense entry flow
main_router.include_router(cash_flow_router)
main_router.include_router(history_router)
main_router.include_router(report_router)
main_router.include_router(import_router)
main_router.include_router(language_router)
main_router.include_router(debug_router)  # Must be last
