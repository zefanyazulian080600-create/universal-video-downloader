"""URL processing, metadata display, and download callback handlers."""

import uuid
from typing import Dict, Optional

from aiogram import F, Router
from aiogram.types import CallbackQuery, Message

from app.bot.keyboards.inline import (
    get_metadata_action_keyboard,
    get_quality_selection_keyboard,
)
from app.config import settings
from app.database.models import User
from app.downloader.extractor import MetadataExtractor
from app.downloader.formats import MediaMetadata
from app.downloader.validator import extract_url_from_text
from app.jobs.manager import job_manager
from app.jobs.queue import JobQueue
from app.utils.errors import AppError, UserJobLimitError
from app.utils.logging import get_logger

logger = get_logger(__name__)

router = Router(name="download_router")

# Cache storing inspected media metadata waiting for user choice
# Format: job_id -> {"url": str, "metadata": MediaMetadata, "user_id": int, "status_msg_id": int}
pending_inspections: Dict[str, Dict] = {}

# Reference to active JobQueue (injected on startup)
_job_queue: Optional[JobQueue] = None


def set_job_queue(queue: JobQueue) -> None:
    """Inject JobQueue dependency into download router."""
    global _job_queue
    _job_queue = queue


@router.message(F.text)
async def handle_text_message(message: Message, db_user: User) -> None:
    """Detect and process URLs from text messages or provide friendly guidance."""
    if not message.text or not message.from_user:
        return

    text = message.text.strip()
    if text.startswith("/"):
        # Commands are handled by command handlers
        return

    extracted_url = extract_url_from_text(text)
    if not extracted_url:
        # User sent non-URL message
        await message.answer(
            "👋 <b>Kirimkan tautan video untuk diunduh!</b>\n\n"
            "Contoh:\n"
            "• <code>https://www.youtube.com/watch?v=...</code>\n"
            "• <code>https://vt.tiktok.com/...</code>\n"
            "• <code>https://www.instagram.com/reel/...</code>\n"
            "• <code>https://x.com/.../status/...</code>\n\n"
            "Gunakan /help untuk melihat panduan lengkap.",
            parse_mode="HTML",
        )
        return

    user_id = message.from_user.id

    # 1. Check user concurrent job limit before extraction
    if job_manager.get_user_active_count(user_id) >= settings.max_jobs_per_user:
        await message.answer(
            f"⚠️ <b>Batas Unduhan Tercapai</b>\n\n"
            f"Kamu masih memiliki {settings.max_jobs_per_user} unduhan aktif yang sedang berjalan. "
            f"Tunggu hingga selesai atau gunakan /cancel untuk membatalkannya.",
            parse_mode="HTML",
        )
        return

    # 2. Send status placeholder
    status_msg = await message.answer(
        "🔍 <b>Memeriksa tautan media...</b>\nMohon tunggu sejenak.",
        parse_mode="HTML",
    )

    extractor = MetadataExtractor()
    job_id = str(uuid.uuid4())

    try:
        metadata = await extractor.extract(extracted_url)
    except AppError as e:
        await status_msg.edit_text(
            f"❌ <b>Pemeriksaan Tautan Gagal</b>\n\n{e.user_message}",
            parse_mode="HTML",
        )
        return
    except Exception as e:
        logger.error(f"Unexpected error inspecting URL {extracted_url}: {e}", exc_info=True)
        await status_msg.edit_text(
            "❌ Maaf, tautan ini belum dapat diakses atau platform sedang tidak merespons.",
            parse_mode="HTML",
        )
        return

    # Cache pending inspection data
    pending_inspections[job_id] = {
        "url": extracted_url,
        "metadata": metadata,
        "user_id": user_id,
        "status_msg_id": status_msg.message_id,
    }

    # 3. If user preferred to skip metadata and download immediately
    if not db_user.include_metadata and _job_queue:
        format_spec = metadata.best_format.yt_dlp_format_spec if metadata.best_format else "best"
        is_audio = db_user.preferred_format == "mp3"
        await status_msg.edit_text("⏳ <b>Menyiapkan pengunduhan...</b>", parse_mode="HTML")
        await _job_queue.enqueue(
            job_id=job_id,
            telegram_id=user_id,
            url=extracted_url,
            platform=metadata.platform,
            format_spec="bestaudio/best" if is_audio else format_spec,
            is_audio=is_audio,
            title=metadata.title,
            status_message_id=status_msg.message_id,
        )
        return

    # 4. Display metadata summary card and quality buttons
    summary = metadata.get_summary_card()
    keyboard = get_metadata_action_keyboard(job_id)

    await status_msg.edit_text(
        text=summary,
        reply_markup=keyboard,
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("dl_fast:"))
async def callback_download_fast(callback: CallbackQuery) -> None:
    """Download with best default quality immediately."""
    _, job_id = callback.data.split(":", 1)
    data = pending_inspections.get(job_id)

    if not data or not _job_queue:
        await callback.answer("Sesi unduhan ini telah kedaluwarsa. Silakan kirim ulang tautan.", show_alert=True)
        return

    if callback.from_user.id != data["user_id"]:
        await callback.answer("Tombol ini hanya dapat digunakan oleh pengirim tautan.", show_alert=True)
        return

    await callback.answer("Memulai pengunduhan kualitas terbaik...")
    metadata: MediaMetadata = data["metadata"]
    format_spec = metadata.best_format.yt_dlp_format_spec if metadata.best_format else "best"

    if callback.message:
        await callback.message.edit_reply_markup(reply_markup=None)

    await _job_queue.enqueue(
        job_id=job_id,
        telegram_id=data["user_id"],
        url=data["url"],
        platform=metadata.platform,
        format_spec=format_spec,
        is_audio=False,
        title=metadata.title,
        status_message_id=data["status_msg_id"],
    )


@router.callback_query(F.data.startswith("dl_qualities:"))
async def callback_show_qualities(callback: CallbackQuery) -> None:
    """Display available resolutions keyboard."""
    _, job_id = callback.data.split(":", 1)
    data = pending_inspections.get(job_id)

    if not data:
        await callback.answer("Sesi telah kedaluwarsa. Kirim ulang tautan.", show_alert=True)
        return

    if callback.from_user.id != data["user_id"]:
        await callback.answer("Hanya pengirim tautan yang dapat memilih.", show_alert=True)
        return

    await callback.answer()
    metadata: MediaMetadata = data["metadata"]
    keyboard = get_quality_selection_keyboard(job_id, metadata.formats)

    if callback.message:
        await callback.message.edit_text(
            text=f"🎬 <b>Pilih Kualitas Video:</b>\n{metadata.title[:60]}",
            reply_markup=keyboard,
            parse_mode="HTML",
        )


@router.callback_query(F.data.startswith("dl_audio:"))
async def callback_download_audio(callback: CallbackQuery) -> None:
    """Download audio stream only."""
    _, job_id = callback.data.split(":", 1)
    data = pending_inspections.get(job_id)

    if not data or not _job_queue:
        await callback.answer("Sesi telah kedaluwarsa. Kirim ulang tautan.", show_alert=True)
        return

    if callback.from_user.id != data["user_id"]:
        await callback.answer("Hanya pengirim tautan yang dapat memilih.", show_alert=True)
        return

    await callback.answer("Memulai pengunduhan audio...")
    metadata: MediaMetadata = data["metadata"]

    if callback.message:
        await callback.message.edit_reply_markup(reply_markup=None)

    await _job_queue.enqueue(
        job_id=job_id,
        telegram_id=data["user_id"],
        url=data["url"],
        platform=metadata.platform,
        format_spec="bestaudio/best",
        is_audio=True,
        title=metadata.title,
        status_message_id=data["status_msg_id"],
    )


@router.callback_query(F.data.startswith("dl_fmt:"))
async def callback_download_specific_format(callback: CallbackQuery) -> None:
    """Download specific selected format."""
    parts = callback.data.split(":")
    if len(parts) < 3:
        await callback.answer("Pilihan tidak valid.")
        return

    job_id = parts[1]
    fmt_id = parts[2]
    data = pending_inspections.get(job_id)

    if not data or not _job_queue:
        await callback.answer("Sesi telah kedaluwarsa. Kirim ulang tautan.", show_alert=True)
        return

    if callback.from_user.id != data["user_id"]:
        await callback.answer("Hanya pengirim tautan yang dapat memilih.", show_alert=True)
        return

    metadata: MediaMetadata = data["metadata"]
    selected_fmt = next((f for f in metadata.formats if f.format_id == fmt_id), None)
    format_spec = selected_fmt.yt_dlp_format_spec if selected_fmt else "best"
    is_audio = selected_fmt.is_audio_only if selected_fmt else False

    await callback.answer(f"Memulai pengunduhan {selected_fmt.label if selected_fmt else 'video'}...")

    if callback.message:
        await callback.message.edit_reply_markup(reply_markup=None)

    await _job_queue.enqueue(
        job_id=job_id,
        telegram_id=data["user_id"],
        url=data["url"],
        platform=metadata.platform,
        format_spec=format_spec,
        is_audio=is_audio,
        title=metadata.title,
        status_message_id=data["status_msg_id"],
    )


@router.callback_query(F.data.startswith("dl_cancel:"))
async def callback_cancel_inspection(callback: CallbackQuery) -> None:
    """Cancel pending media download before starting."""
    _, job_id = callback.data.split(":", 1)
    pending_inspections.pop(job_id, None)
    await callback.answer("Unduhan dibatalkan.")
    if callback.message:
        await callback.message.edit_text("❌ <b>Proses dibatalkan oleh pengguna.</b>", parse_mode="HTML")
