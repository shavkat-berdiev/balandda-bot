from aiogram import Router

from bot.handlers.language import router as language_router
from bot.handlers.start import router as start_router

# Import order matters — more specific routers first
main_router = Router()
main_router.include_router(start_router)
main_router.include_router(language_router)
