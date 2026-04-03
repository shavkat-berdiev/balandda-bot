"""Shared bot utilities."""

import logging
from aiogram import types
from aiogram.exceptions import TelegramBadRequest

logger = logging.getLogger(__name__)


async def safe_edit_text(message: types.Message, text: str, **kwargs) -> types.Message | None:
    """Edit message text, suppressing 'message is not modified' errors.

    Returns the edited message on success, or None if edit was suppressed.
    """
    try:
        return await message.edit_text(text, **kwargs)
    except TelegramBadRequest as e:
        if "message is not modified" in str(e):
            logger.debug("Suppressed 'message is not modified' error")
            return None
        raise


async def safe_edit_or_answer(message: types.Message, text: str, edit: bool = True, **kwargs) -> types.Message:
    """Edit message if edit=True, otherwise send a new message.

    Use edit=True for callback-initiated messages (bot's own messages).
    Use edit=False for user-initiated messages (can't edit those).
    """
    if edit:
        result = await safe_edit_text(message, text, **kwargs)
        return result or message
    else:
        return await message.answer(text, **kwargs)
