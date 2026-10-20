"""User preferences and configuration handlers."""

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from app.bot.keyboards.inline import get_quality_picker_keyboard, get_settings_keyboard
from app.database.models import User
from app.database.repository import UserRepository
from app.database.session import get_db_session

router = Router(name="settings_router")


@router.message(Command("settings"))
async def handle_settings_cmd(message: Message, db_user: User) -> None:
    """Show settings menu on /settings command."""
    text = (
        "⚙️ <b>Pengaturan Pengunduhan Anda</b>\n\n"
        "Sesuaikan preferensi default pengunduhan video dan audio di bawah ini. "
        "Perubahan akan tersimpan secara otomatis."
    )
    await message.answer(
        text=text,
        reply_markup=get_settings_keyboard(db_user),
        parse_mode="HTML",
    )


@router.message(Command("quality"))
async def handle_quality_cmd(message: Message) -> None:
    """Show quick quality picker on /quality command."""
    text = (
        "🎯 <b>Pilih Kualitas Default Baru</b>\n\n"
        "Pilih resolusi video yang kamu inginkan sebagai pilihan bawaan setiap kali mengirim link:"
    )
    await message.answer(
        text=text,
        reply_markup=get_quality_picker_keyboard(),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "nav_settings")
async def callback_nav_settings(callback: CallbackQuery, db_user: User) -> None:
    """Return to settings menu via inline button."""
    await callback.answer()
    text = (
        "⚙️ <b>Pengaturan Pengunduhan Anda</b>\n\n"
        "Sesuaikan preferensi default pengunduhan video dan audio di bawah ini."
    )
    if callback.message:
        await callback.message.edit_text(
            text=text,
            reply_markup=get_settings_keyboard(db_user),
            parse_mode="HTML",
        )


@router.callback_query(F.data == "set_qual_menu")
async def callback_quality_menu(callback: CallbackQuery) -> None:
    """Show quality selection keyboard."""
    await callback.answer()
    text = "🎯 <b>Pilih Kualitas Default Baru</b>\nPilih resolusi video bawaan:"
    if callback.message:
        await callback.message.edit_text(
            text=text,
            reply_markup=get_quality_picker_keyboard(),
            parse_mode="HTML",
        )


@router.callback_query(F.data.startswith("set_q:"))
async def callback_set_quality_choice(callback: CallbackQuery, db_user: User) -> None:
    """Save selected quality to user profile in database."""
    _, choice = callback.data.split(":", 1)
    async with get_db_session() as session:
        updated_user = await UserRepository.update_preferences(
            session=session,
            telegram_id=callback.from_user.id,
            default_quality=choice,
        )
    await callback.answer(f"Kualitas default diubah ke {choice.upper()}!")
    if callback.message and updated_user:
        await callback.message.edit_text(
            text="⚙️ <b>Pengaturan Pengunduhan Anda</b>\n\nPreferensi kualitas berhasil diperbarui.",
            reply_markup=get_settings_keyboard(updated_user),
            parse_mode="HTML",
        )


@router.callback_query(F.data == "set_toggle_format")
async def callback_toggle_format(callback: CallbackQuery, db_user: User) -> None:
    """Toggle between preferred format mp4 and mp3."""
    new_format = "mp3" if db_user.preferred_format == "mp4" else "mp4"
    async with get_db_session() as session:
        updated_user = await UserRepository.update_preferences(
            session=session,
            telegram_id=callback.from_user.id,
            preferred_format=new_format,
        )
    await callback.answer(f"Format utama diubah ke {new_format.upper()}!")
    if callback.message and updated_user:
        await callback.message.edit_reply_markup(reply_markup=get_settings_keyboard(updated_user))


@router.callback_query(F.data == "set_toggle_meta")
async def callback_toggle_meta(callback: CallbackQuery, db_user: User) -> None:
    """Toggle whether media info card is shown before downloading."""
    new_val = not db_user.include_metadata
    async with get_db_session() as session:
        updated_user = await UserRepository.update_preferences(
            session=session,
            telegram_id=callback.from_user.id,
            include_metadata=new_val,
        )
    state_str = "diaktifkan" if new_val else "dinonaktifkan"
    await callback.answer(f"Pratinjau info {state_str}!")
    if callback.message and updated_user:
        await callback.message.edit_reply_markup(reply_markup=get_settings_keyboard(updated_user))


@router.callback_query(F.data == "set_toggle_compress")
async def callback_toggle_compress(callback: CallbackQuery, db_user: User) -> None:
    """Toggle automatic video compression preference."""
    new_val = not db_user.enable_compression
    async with get_db_session() as session:
        updated_user = await UserRepository.update_preferences(
            session=session,
            telegram_id=callback.from_user.id,
            enable_compression=new_val,
        )
    state_str = "diaktifkan" if new_val else "dinonaktifkan"
    await callback.answer(f"Kompresi otomatis {state_str}!")
    if callback.message and updated_user:
        await callback.message.edit_reply_markup(reply_markup=get_settings_keyboard(updated_user))
