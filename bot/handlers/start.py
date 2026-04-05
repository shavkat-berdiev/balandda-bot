import logging

from aiogram import Bot, F, Router, types
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import select

from bot.config import settings
from bot.keyboards.main import main_menu_keyboard, section_keyboard
from bot.locales import get_text
from db.database import async_session
from db.enums import RegistrationRequestStatus, UserRole
from db.models import BusinessUnit, Language, RegistrationRequest, User, UserRole as UserRoleEnum

router = Router()
logger = logging.getLogger(__name__)


class RegistrationStates(StatesGroup):
    waiting_confirm = State()


async def get_or_create_user(telegram_id: int, full_name: str) -> User | None:
    """Get existing user or return None if not authorized."""
    async with async_session() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == telegram_id)
        )
        user = result.scalar_one_or_none()
        if user:
            # Update name if changed
            if user.full_name != full_name:
                user.full_name = full_name
                await session.commit()
        return user


async def create_admin_if_needed(telegram_id: int, full_name: str) -> User:
    """Create admin user (first-time setup)."""
    async with async_session() as session:
        user = User(
            telegram_id=telegram_id,
            full_name=full_name,
            role=UserRoleEnum.ADMIN,
            language=Language.RU,
            active_section=BusinessUnit.RESORT,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user


async def _notify_admins(bot: Bot, text: str):
    """Send notification to all admin users."""
    async with async_session() as session:
        result = await session.execute(
            select(User).where(User.role == UserRoleEnum.ADMIN, User.is_active == True)
        )
        admins = result.scalars().all()

    for admin in admins:
        try:
            await bot.send_message(admin.telegram_id, text)
        except Exception as e:
            logger.error(f"Failed to notify admin {admin.telegram_id}: {e}")


@router.message(CommandStart())
async def cmd_start(message: types.Message, state: FSMContext):
    """Handle /start command."""
    user = await get_or_create_user(message.from_user.id, message.from_user.full_name)

    if user is None:
        # Check if this is the admin (first user)
        if settings.admin_user_id and message.from_user.id == settings.admin_user_id:
            user = await create_admin_if_needed(
                message.from_user.id, message.from_user.full_name
            )
        else:
            # Check if any users exist (first user becomes admin)
            async with async_session() as session:
                result = await session.execute(select(User))
                if not result.scalars().first():
                    user = await create_admin_if_needed(
                        message.from_user.id, message.from_user.full_name
                    )
                else:
                    # Not authorized — check if they already have a pending request
                    result = await session.execute(
                        select(RegistrationRequest).where(
                            RegistrationRequest.telegram_id == message.from_user.id,
                            RegistrationRequest.status == RegistrationRequestStatus.PENDING,
                        )
                    )
                    existing = result.scalar_one_or_none()

                    if existing:
                        await message.answer(
                            "⏳ Ваша заявка уже отправлена и ожидает рассмотрения.\n"
                            "Администратор скоро примет решение."
                        )
                    else:
                        buttons = [
                            [InlineKeyboardButton(
                                text="📩 Отправить заявку",
                                callback_data="reg:request",
                            )],
                        ]
                        await message.answer(
                            "👋 Добро пожаловать!\n\n"
                            "Вы ещё не зарегистрированы в системе.\n"
                            "Нажмите кнопку ниже, чтобы отправить заявку администратору.",
                            reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
                        )
                    return

    lang = user.language.value.lower()
    await message.answer(
        get_text("welcome", lang),
        reply_markup=section_keyboard(lang),
    )


# ── Registration request ──────────────────────────────────────────


@router.callback_query(F.data == "reg:request")
async def on_registration_request(callback: types.CallbackQuery, state: FSMContext):
    """User wants to send a registration request."""
    telegram_id = callback.from_user.id
    full_name = callback.from_user.full_name or "Unknown"
    username = callback.from_user.username

    async with async_session() as session:
        # Check for existing pending request
        result = await session.execute(
            select(RegistrationRequest).where(
                RegistrationRequest.telegram_id == telegram_id,
                RegistrationRequest.status == RegistrationRequestStatus.PENDING,
            )
        )
        existing = result.scalar_one_or_none()

        if existing:
            await callback.message.edit_text(
                "⏳ Ваша заявка уже отправлена и ожидает рассмотрения."
            )
            await callback.answer()
            return

        # Check for rejected request (allow resubmit)
        # Create new request
        req = RegistrationRequest(
            telegram_id=telegram_id,
            full_name=full_name,
            username=username,
            status=RegistrationRequestStatus.PENDING,
        )
        session.add(req)
        await session.commit()

    await callback.message.edit_text(
        "✅ Заявка отправлена!\n\n"
        "Администратор рассмотрит вашу заявку и назначит роль.\n"
        "Вы получите уведомление, когда заявка будет обработана."
    )
    await callback.answer()

    # Notify all admins
    username_str = f" (@{username})" if username else ""
    await _notify_admins(
        callback.bot,
        f"📩 <b>Новая заявка на регистрацию</b>\n\n"
        f"Имя: {full_name}{username_str}\n"
        f"ID: <code>{telegram_id}</code>\n\n"
        f"Откройте панель управления для рассмотрения.",
    )


# ── Admin approval via bot callback (from admin panel notification) ──


@router.callback_query(F.data.startswith("reg_approve:"))
async def on_approve_from_bot(callback: types.CallbackQuery, state: FSMContext):
    """Quick approve from bot notification (admin only)."""
    # Verify caller is admin
    async with async_session() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == callback.from_user.id)
        )
        admin = result.scalar_one_or_none()
        if not admin or admin.role != UserRoleEnum.ADMIN:
            await callback.answer("Только администраторы", show_alert=True)
            return

    # This callback is just informational — actual approval happens in admin panel
    await callback.answer("Откройте панель управления для назначения роли", show_alert=True)


# ── Section selection & menu ──────────────────────────────────────


@router.callback_query(lambda c: c.data and c.data.startswith("section:"))
async def on_section_select(callback: types.CallbackQuery):
    """Handle section selection."""
    section = callback.data.split(":")[1]
    business_unit = BusinessUnit(section.upper())

    async with async_session() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == callback.from_user.id)
        )
        user = result.scalar_one_or_none()
        if not user:
            await callback.answer()
            return

        user.active_section = business_unit
        await session.commit()
        lang = user.language.value.lower()

    section_name = get_text(f"section_{section}", lang)
    await callback.message.edit_text(
        get_text("main_menu", lang, section=section_name),
        reply_markup=main_menu_keyboard(lang, current_section=section),
    )
    await callback.answer(get_text("switched_to", lang, section=section_name))


@router.message(Command("menu"))
async def cmd_menu(message: types.Message):
    """Show main menu for current section."""
    user = await get_or_create_user(message.from_user.id, message.from_user.full_name)
    if not user:
        await message.answer(get_text("not_authorized"))
        return

    lang = user.language.value.lower()
    section = user.active_section.value.lower()
    section_name = get_text(f"section_{section}", lang)
    await message.answer(
        get_text("main_menu", lang, section=section_name),
        reply_markup=main_menu_keyboard(lang, current_section=section),
    )
