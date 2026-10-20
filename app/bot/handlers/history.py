"""User job history, active job status, and cancellation handlers."""

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from app.database.repository import JobRepository
from app.database.session import get_db_session
from app.jobs.manager import job_manager
from app.utils.filenames import format_duration, format_file_size

router = Router(name="history_router")


STATUS_EMOJIS = {
    "completed": "✅ Selesai",
    "failed": "❌ Gagal",
    "cancelled": "⏹ Dibatalkan",
    "downloading": "⏳ Mengunduh",
    "processing": "⚙️ Memproses",
    "uploading": "📤 Mengirim",
    "queued": "⌛️ Antrean",
    "inspecting": "🔍 Memeriksa",
}


@router.message(Command("history"))
async def handle_history(message: Message) -> None:
    """Show the user's private download history."""
    if not message.from_user:
        return

    telegram_id = message.from_user.id
    async with get_db_session() as session:
        jobs = await JobRepository.get_user_history(session, telegram_id, limit=8)

    if not jobs:
        await message.answer(
            "📋 <b>Riwayat Unduhan</b>\n\n"
            "Kamu belum memiliki riwayat unduhan media. Kirimkan tautan video untuk memulai!",
            parse_mode="HTML",
        )
        return

    lines = ["📋 <b>Riwayat Unduhan Terakhir</b>", "━━━━━━━━━━━━━━━━━━━━━"]
    for i, job in enumerate(jobs, 1):
        status_text = STATUS_EMOJIS.get(job.status, job.status)
        date_str = job.created_at.strftime("%d/%m/%Y %H:%M") if job.created_at else "-"
        title = job.title or "Media"
        if len(title) > 35:
            title = title[:32] + "..."

        details = []
        if job.duration:
            details.append(format_duration(job.duration))
        if job.file_size_bytes:
            details.append(format_file_size(job.file_size_bytes))

        detail_str = f" ({', '.join(details)})" if details else ""

        lines.append(f"{i}. <b>{title}</b>{detail_str}")
        lines.append(f"   Platform: {job.platform} | Status: {status_text}")
        lines.append(f"   Waktu: <code>{date_str}</code>")
        lines.append("")

    await message.answer("\n".join(lines), parse_mode="HTML")


@router.message(Command("status"))
async def handle_status(message: Message) -> None:
    """Show current active downloads for this user."""
    if not message.from_user:
        return

    telegram_id = message.from_user.id
    async with get_db_session() as session:
        active_jobs = await JobRepository.get_active_jobs_for_user(session, telegram_id)

    if not active_jobs:
        await message.answer(
            "ℹ️ <b>Status Unduhan</b>\n\n"
            "Saat ini tidak ada proses unduhan aktif milikmu yang sedang berjalan.",
            parse_mode="HTML",
        )
        return

    lines = [f"🔄 <b>Unduhan Aktif ({len(active_jobs)})</b>", "━━━━━━━━━━━━━━━━━━━━━"]
    for job in active_jobs:
        status_text = STATUS_EMOJIS.get(job.status, job.status)
        title = job.title or "Video"
        lines.append(f"• <b>{title}</b>")
        lines.append(f"  ID: <code>{job.id[:8]}...</code> | Platform: {job.platform}")
        lines.append(f"  Status: {status_text}")
        lines.append("")

    lines.append("<i>Gunakan /cancel untuk membatalkan unduhan yang sedang berjalan.</i>")
    await message.answer("\n".join(lines), parse_mode="HTML")


@router.message(Command("cancel"))
async def handle_cancel(message: Message) -> None:
    """Cancel all active jobs for the requesting user."""
    if not message.from_user:
        return

    telegram_id = message.from_user.id
    cancelled_ids = await job_manager.cancel_user_jobs(telegram_id)

    if cancelled_ids:
        await message.answer(
            f"⏹ <b>Berhasil Dibatalkan</b>\n\n"
            f"Sebanyak {len(cancelled_ids)} proses unduhan milikmu telah dibatalkan. "
            f"File sementara telah dibersihkan secara aman.",
            parse_mode="HTML",
        )
    else:
        await message.answer(
            "ℹ️ Tidak ada unduhan aktif milikmu yang dapat dibatalkan saat ini.",
            parse_mode="HTML",
        )
