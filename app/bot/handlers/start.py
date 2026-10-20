"""Start, help, platforms, about, and general fallback message handlers."""

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, Message

from app.bot.keyboards.inline import get_start_keyboard
from app.config import settings

router = Router(name="start_router")


WELCOME_TEXT = (
    "👋 <b>Halo! Selamat datang di LinkGrabber Bot.</b>\n\n"
    "Kirimkan tautan video publik yang ingin kamu unduh. Aku akan memeriksa tautan tersebut, "
    "menampilkan informasi media yang tersedia, lalu membantu mengunduhnya jika didukung.\n\n"
    "⚠️ <b>Ketentuan Penggunaan:</b>\n"
    "Gunakan bot ini hanya untuk konten yang kamu miliki atau berhak mengunduhnya sesuai "
    "dengan ketentuan platform dan hukum hak cipta yang berlaku.\n\n"
    "Silakan pilih menu di bawah ini untuk memulai:"
)

HELP_TEXT = (
    "📖 <b>Panduan Penggunaan LinkGrabber Bot</b>\n\n"
    "1️⃣ <b>Kirim Tautan:</b> Cukup salin tautan video dan kirimkan ke chat ini.\n"
    "2️⃣ <b>Pilih Opsi:</b> Bot akan memeriksa video dan menampilkan opsi kualitas atau audio.\n"
    "3️⃣ <b>Terima File:</b> Video akan diunduh dan dikirimkan langsung ke chat Telegram kamu.\n\n"
    "📌 <b>Daftar Perintah (Commands):</b>\n"
    "• /start - Menampilkan menu utama dan sambutan\n"
    "• /help - Panduan penggunaan dan tips\n"
    "• /platforms - Daftar platform yang didukung\n"
    "• /settings - Pengaturan kualitas & format bawaan\n"
    "• /quality - Pintasan cepat mengubah kualitas default\n"
    "• /status - Cek proses unduhan aktif milikmu\n"
    "• /cancel - Batalkan unduhan aktif milikmu\n"
    "• /history - Riwayat unduhan terakhir milikmu\n"
    "• /about - Informasi versi dan teknologi bot\n\n"
    "💡 <i>Catatan: Batas pengiriman bot Telegram standar adalah 50 MB per file.</i>"
)

PLATFORMS_TEXT = (
    "🌐 <b>Platform yang Didukung</b>\n\n"
    "<b>Prioritas Utama:</b>\n"
    "• <b>YouTube</b> (Video Publik & Shorts)\n"
    "• <b>TikTok</b> (Video Publik)\n"
    "• <b>Instagram</b> (Reels & Video Post Publik)\n"
    "• <b>Facebook</b> (Video Publik)\n"
    "• <b>X (Twitter)</b> (Video pada Post Publik)\n"
    "• <b>Vimeo</b> (Video Publik)\n\n"
    "<b>Platform Lain & Tambahan:</b>\n"
    "• Reddit, Pinterest, Threads, Dailymotion, Twitch Clips, SoundCloud\n"
    "• Tautan langsung ke file media (.mp4, .webm, .mp3, dll.)\n\n"
    "🔒 <i>Bot tidak mendukung video dari akun privat, konten berbayar, "
    "atau konten yang dilindungi DRM/login.</i>"
)

ABOUT_TEXT = (
    "ℹ️ <b>Tentang LinkGrabber Bot</b>\n\n"
    "<b>Versi:</b> 1.0.0 (Production Ready)\n"
    "<b>Engine Ekstraksi:</b> yt-dlp & FFmpeg\n"
    "<b>Framework:</b> Python 3.12 + aiogram 3.x\n"
    "<b>Arsitektur:</b> Async Event-driven + SQLAlchemy 2.x\n\n"
    "Dibuat dengan standar performa tinggi, aman dari ancaman SSRF/injeksi, "
    "serta mendukung pemrosesan media berbasis antrean berbatas."
)


@router.message(CommandStart())
async def handle_start(message: Message) -> None:
    """Handle /start command."""
    await message.answer(
        text=WELCOME_TEXT,
        reply_markup=get_start_keyboard(),
        parse_mode="HTML",
    )


@router.message(Command("help"))
async def handle_help(message: Message) -> None:
    """Handle /help command."""
    await message.answer(
        text=HELP_TEXT,
        parse_mode="HTML",
    )


@router.message(Command("platforms"))
async def handle_platforms(message: Message) -> None:
    """Handle /platforms command."""
    await message.answer(
        text=PLATFORMS_TEXT,
        parse_mode="HTML",
    )


@router.message(Command("about"))
async def handle_about(message: Message) -> None:
    """Handle /about command."""
    await message.answer(
        text=ABOUT_TEXT,
        parse_mode="HTML",
    )


@router.callback_query(F.data == "nav_help")
async def callback_nav_help(callback: CallbackQuery) -> None:
    """Navigation callback for help."""
    await callback.answer()
    if callback.message:
        await callback.message.answer(HELP_TEXT, parse_mode="HTML")


@router.callback_query(F.data == "nav_platforms")
async def callback_nav_platforms(callback: CallbackQuery) -> None:
    """Navigation callback for supported platforms."""
    await callback.answer()
    if callback.message:
        await callback.message.answer(PLATFORMS_TEXT, parse_mode="HTML")


@router.callback_query(F.data == "nav_about")
async def callback_nav_about(callback: CallbackQuery) -> None:
    """Navigation callback for about information."""
    await callback.answer()
    if callback.message:
        await callback.message.answer(ABOUT_TEXT, parse_mode="HTML")


@router.callback_query(F.data == "nav_close")
async def callback_nav_close(callback: CallbackQuery) -> None:
    """Close menu callback."""
    await callback.answer("Menu ditutup.")
    if callback.message:
        try:
            await callback.message.delete()
        except Exception:
            pass
