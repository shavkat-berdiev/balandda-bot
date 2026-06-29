import logging

from aiogram import Bot, F, Router, types
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from datetime import datetime
from sqlalchemy import select

from bot.config import settings
from bot.keyboards.main import main_menu_keyboard, section_keyboard
from bot.locales import get_text
from db.database import async_session
from db.enums import RegistrationRequestStatus
from db.models import BusinessUnit, Language, RegistrationRequest, User, UserRole

router = Router()
logger = logging.getLogger(__name__)

ROLE_LABELS = {
    "OWNER": "Владелец", "ADMIN": "Администратор",
    "RESORT_MANAGER": "Менеджер курорта", "RESTAURANT_MANAGER": "Менеджер ресторана",
    "OPERATOR": "Оператор", "PURCHASER": "Закупщик",
}
CALENDAR_URL = "https://calendar.balandda.uz"


def _approve_keyboard(req_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Оператор", callback_data=f"reg_ok:{req_id}:OPERATOR"),
         InlineKeyboardButton(text="✅ Менеджер", callback_data=f"reg_ok:{req_id}:RESORT_MANAGER")],
        [InlineKeyboardButton(text="✅ Админ", callback_data=f"reg_ok:{req_id}:ADMIN"),
         InlineKeyboardButton(text="❌ Отклонить", callback_data=f"reg_no:{req_id}")],
    ])


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
            role=UserRole.ADMIN,
            language=Language.RU,
            active_section=BusinessUnit.RESORT,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user


async def _notify_admins(bot: Bot, text: str, reply_markup=None):
    """Send notification to all admin/owner users."""
    async with async_session() as session:
        result = await session.execute(
            select(User).where(
                User.role.in_([UserRole.ADMIN, UserRole.OWNER]), User.is_active == True
            )
        )
        admins = result.scalars().all()

    for admin in admins:
        try:
            await bot.send_message(admin.telegram_id, text, reply_markup=reply_markup)
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
        await session.refresh(req)
        new_req_id = req.id

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
        f"Выберите роль для одобрения:",
        reply_markup=_approve_keyboard(new_req_id),
    )


# ── Admin approval via bot callback (from admin panel notification) ──


@router.callback_query(F.data.startswith("reg_ok:"))
async def on_reg_approve(callback: types.CallbackQuery, state: FSMContext):
    """Approve a registration request straight from the Telegram notification."""
    parts = callback.data.split(":")
    req_id, role_str = int(parts[1]), parts[2]
    async with async_session() as session:
        admin = (await session.execute(
            select(User).where(User.telegram_id == callback.from_user.id)
        )).scalar_one_or_none()
        if not admin or admin.role not in (UserRole.ADMIN, UserRole.OWNER):
            return await callback.answer("Только администраторы", show_alert=True)
        req = await session.get(RegistrationRequest, req_id)
        if not req:
            return await callback.answer("Заявка не найдена", show_alert=True)
        if req.status != RegistrationRequestStatus.PENDING:
            return await callback.answer("Заявка уже обработана", show_alert=True)
        try:
            role = UserRole(role_str)
        except ValueError:
            return await callback.answer("Неверная роль", show_alert=True)
        exists = (await session.execute(
            select(User).where(User.telegram_id == req.telegram_id)
        )).scalar_one_or_none()
        if not exists:
            session.add(User(
                telegram_id=req.telegram_id, full_name=req.full_name, role=role,
                language=Language.RU, active_section=BusinessUnit.RESORT,
            ))
        req.status = RegistrationRequestStatus.APPROVED
        req.assigned_role = role
        req.reviewed_by = callback.from_user.id
        req.reviewed_at = datetime.utcnow()
        await session.commit()
        applicant_id, applicant_name = req.telegram_id, req.full_name

    label = ROLE_LABELS.get(role_str, role_str)
    try:
        await callback.message.edit_text(
            f"✅ <b>{applicant_name}</b> принят как «{label}»\n(одобрил: {callback.from_user.full_name})"
        )
    except Exception:
        pass
    try:
        await callback.bot.send_message(
            applicant_id,
            f"✅ Ваша заявка одобрена! Роль: <b>{label}</b>.\n\nВойдите: {CALENDAR_URL}",
        )
    except Exception as e:
        logger.error(f"notify applicant failed: {e}")
    await callback.answer("Одобрено")


@router.callback_query(F.data.startswith("reg_no:"))
async def on_reg_reject(callback: types.CallbackQuery, state: FSMContext):
    """Reject a registration request from the Telegram notification."""
    req_id = int(callback.data.split(":")[1])
    async with async_session() as session:
        admin = (await session.execute(
            select(User).where(User.telegram_id == callback.from_user.id)
        )).scalar_one_or_none()
        if not admin or admin.role not in (UserRole.ADMIN, UserRole.OWNER):
            return await callback.answer("Только администраторы", show_alert=True)
        req = await session.get(RegistrationRequest, req_id)
        if not req or req.status != RegistrationRequestStatus.PENDING:
            return await callback.answer("Недоступно", show_alert=True)
        req.status = RegistrationRequestStatus.REJECTED
        req.reviewed_by = callback.from_user.id
        req.reviewed_at = datetime.utcnow()
        await session.commit()
        applicant_id, applicant_name = req.telegram_id, req.full_name

    try:
        await callback.message.edit_text(
            f"❌ Заявка от <b>{applicant_name}</b> отклонена\n(отклонил: {callback.from_user.full_name})"
        )
    except Exception:
        pass
    try:
        await callback.bot.send_message(applicant_id, "К сожалению, ваша заявка отклонена.")
    except Exception:
        pass
    await callback.answer("Отклонено")


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
        reply_markup=main_menu_keyboard(lang, current_section=section, role=user.role.value),
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
        reply_markup=main_menu_keyboard(lang, current_section=section, role=user.role.value),
    )
