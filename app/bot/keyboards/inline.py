"""Inline keyboards for interactive navigation, format selection, and user settings."""

from typing import List

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.database.models import User
from app.downloader.formats import MediaFormatOption


def get_start_keyboard() -> InlineKeyboardMarkup:
    """Main menu navigation keyboard."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📖 Panduan", callback_data="nav_help"),
                InlineKeyboardButton(text="🌐 Platform", callback_data="nav_platforms"),
            ],
            [
                InlineKeyboardButton(text="⚙️ Pengaturan", callback_data="nav_settings"),
                InlineKeyboardButton(text="ℹ️ Tentang", callback_data="nav_about"),
            ],
        ]
    )


def get_metadata_action_keyboard(job_id: str) -> InlineKeyboardMarkup:
    """Action buttons displayed under inspected media metadata card."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="⭐️ Download Terbaik", callback_data=f"dl_fast:{job_id}"),
            ],
            [
                InlineKeyboardButton(text="🎬 Pilih Kualitas", callback_data=f"dl_qualities:{job_id}"),
                InlineKeyboardButton(text="🎵 Audio Saja", callback_data=f"dl_audio:{job_id}"),
            ],
            [
                InlineKeyboardButton(text="❌ Batalkan", callback_data=f"dl_cancel:{job_id}"),
            ],
        ]
    )


def get_quality_selection_keyboard(
    job_id: str,
    formats: List[MediaFormatOption],
) -> InlineKeyboardMarkup:
    """Dynamic resolution selection keyboard based on available formats."""
    buttons: List[List[InlineKeyboardButton]] = []

    for fmt in formats:
        # Skip best option here as it's the default fast action
        if fmt.resolution_label == "best":
            continue

        size_label = f" ({fmt.formatted_size})" if fmt.filesize else ""
        btn_text = f"{fmt.label}{size_label}"
        buttons.append(
            [InlineKeyboardButton(text=btn_text, callback_data=f"dl_fmt:{job_id}:{fmt.format_id}")]
        )

    # Navigation buttons
    buttons.append(
        [
            InlineKeyboardButton(text="⭐️ Kualitas Terbaik", callback_data=f"dl_fast:{job_id}"),
            InlineKeyboardButton(text="🔙 Kembali", callback_data=f"dl_cancel:{job_id}"),
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_settings_keyboard(user: User) -> InlineKeyboardMarkup:
    """Settings menu keyboard allowing user to toggle download preferences."""
    meta_icon = "✅" if user.include_metadata else "❌"
    compress_icon = "✅" if user.enable_compression else "❌"

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"🎯 Kualitas Default: {user.default_quality.upper()}",
                    callback_data="set_qual_menu",
                )
            ],
            [
                InlineKeyboardButton(
                    text=f"📁 Format: {user.preferred_format.upper()}",
                    callback_data="set_toggle_format",
                )
            ],
            [
                InlineKeyboardButton(
                    text=f"📋 Pratinjau Info: {meta_icon}",
                    callback_data="set_toggle_meta",
                )
            ],
            [
                InlineKeyboardButton(
                    text=f"🗜 Kompresi Otomatis: {compress_icon}",
                    callback_data="set_toggle_compress",
                )
            ],
            [
                InlineKeyboardButton(text="🔙 Tutup Menu", callback_data="nav_close"),
            ],
        ]
    )


def get_quality_picker_keyboard() -> InlineKeyboardMarkup:
    """Picker for changing default download quality."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⭐️ Terbaik (Auto)", callback_data="set_q:best")],
            [
                InlineKeyboardButton(text="🎬 1080p (Full HD)", callback_data="set_q:1080p"),
                InlineKeyboardButton(text="🎬 720p (HD)", callback_data="set_q:720p"),
            ],
            [
                InlineKeyboardButton(text="🎬 480p (SD)", callback_data="set_q:480p"),
                InlineKeyboardButton(text="🎬 360p", callback_data="set_q:360p"),
            ],
            [InlineKeyboardButton(text="🎵 Audio Saja", callback_data="set_q:audio")],
            [InlineKeyboardButton(text="🔙 Kembali ke Pengaturan", callback_data="nav_settings")],
        ]
    )
