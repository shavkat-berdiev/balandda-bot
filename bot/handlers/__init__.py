from aiogram import Router

from bot.handlers.cash_flow import router as cash_flow_router
from bot.handlers.history import router as history_router
from bot.handlers.import_report import router as import_router
from bot.handlers.language import router as language_router
from bot.handlers.report import router as report_router
from bot.handlers.start import router as start_router

# Import order matters — more specific routers first
main_router = Router()
main_router.include_router(start_router)
main_router.include_router(cash_flow_router)
main_router.include_router(history_router)
main_router.include_router(report_router)
main_router.include_router(import_router)  # Text message handler — must be after specific handlers
main_router.include_router(language_router)
