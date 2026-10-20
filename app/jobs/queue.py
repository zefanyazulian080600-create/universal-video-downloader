"""Asynchronous job queue and worker execution pipeline.

Enforces global and per-user concurrency limits, updates progress periodically,
handles cancellations, and guarantees resource cleanup.
"""

import asyncio
from pathlib import Path
from typing import Optional

from aiogram import Bot

from app.config import settings
from app.database.repository import JobRepository
from app.database.session import get_db_session
from app.downloader.progress import DownloadProgressTracker
from app.downloader.service import DownloaderService
from app.jobs.cleanup import clean_job_directory
from app.jobs.manager import job_manager
from app.services.telegram_service import TelegramService
from app.utils.errors import (
    AppError,
    JobCancelledError,
    QueueFullError,
    UserJobLimitError,
)
from app.utils.logging import get_logger

logger = get_logger(__name__)


class JobQueue:
    """Manages worker concurrency and execution pipeline for media downloads."""

    def __init__(self, bot: Bot, downloader_service: Optional[DownloaderService] = None):
        self.bot = bot
        self.downloader = downloader_service or DownloaderService()
        self.telegram_service = TelegramService(bot)
        self.semaphore = asyncio.Semaphore(settings.max_concurrent_downloads)

    async def enqueue(
        self,
        job_id: str,
        telegram_id: int,
        url: str,
        platform: str,
        format_spec: str = "best",
        is_audio: bool = False,
        title: str = "Video",
        status_message_id: Optional[int] = None,
    ) -> str:
        """Validate user limits and submit download task to execution pool."""
        # 1. Check user concurrent job limit
        user_active = job_manager.get_user_active_count(telegram_id)
        if user_active >= settings.max_jobs_per_user:
            raise UserJobLimitError(max_jobs=settings.max_jobs_per_user)

        # 2. Check global queue capacity
        total_active = job_manager.get_total_active_count()
        if total_active >= settings.max_concurrent_downloads * 3:
            raise QueueFullError()

        # 3. Create job record in database
        async with get_db_session() as session:
            await JobRepository.create_job(
                session=session,
                job_id=job_id,
                telegram_id=telegram_id,
                url_sanitized=url,
                platform=platform,
                title=title,
            )

        # 4. Initialize progress tracker
        tracker = DownloadProgressTracker()

        # 5. Register in JobManager and launch background worker task
        active_job = await job_manager.register(
            job_id=job_id,
            telegram_id=telegram_id,
            progress_tracker=tracker,
        )

        task = asyncio.create_task(
            self._worker(
                job_id=job_id,
                telegram_id=telegram_id,
                url=url,
                format_spec=format_spec,
                is_audio=is_audio,
                title=title,
                tracker=tracker,
                status_message_id=status_message_id,
            )
        )
        await job_manager.attach_task(job_id, task)
        return job_id

    async def _worker(
        self,
        job_id: str,
        telegram_id: int,
        url: str,
        format_spec: str,
        is_audio: bool,
        title: str,
        tracker: DownloadProgressTracker,
        status_message_id: Optional[int],
    ) -> None:
        """Background worker executing download, tracking progress, and delivering media."""
        job_dir = settings.temp_dir / job_id
        progress_task: Optional[asyncio.Task] = None

        try:
            # Inform user if waiting in queue
            if self.semaphore.locked() and status_message_id:
                await self.telegram_service.edit_status_text(
                    chat_id=telegram_id,
                    message_id=status_message_id,
                    text="⏳ Menunggu antrean pengunduhan server...",
                )

            async with self.semaphore:
                if tracker.is_cancelled:
                    raise JobCancelledError()

                # Update database: downloading
                async with get_db_session() as session:
                    await JobRepository.update_status(session, job_id, "downloading")

                # Start periodic status message updater
                if status_message_id:
                    progress_task = asyncio.create_task(
                        self._periodic_status_updater(
                            telegram_id=telegram_id,
                            status_message_id=status_message_id,
                            tracker=tracker,
                            title=title,
                        )
                    )

                # Execute download
                media_result = await self.downloader.download(
                    job_id=job_id,
                    url=url,
                    job_dir=job_dir,
                    format_spec=format_spec,
                    is_audio=is_audio,
                    progress_tracker=tracker,
                    title=title,
                )

                # Stop progress updater
                if progress_task and not progress_task.done():
                    progress_task.cancel()

                # Update database: uploading
                async with get_db_session() as session:
                    await JobRepository.update_status(
                        session=session,
                        job_id=job_id,
                        status="uploading",
                        file_size=media_result.file_size_bytes,
                        duration=media_result.duration,
                    )

                if status_message_id:
                    await self.telegram_service.edit_status_text(
                        chat_id=telegram_id,
                        message_id=status_message_id,
                        text="📤 <b>Mengirim media ke Telegram...</b>\nMohon tunggu sejenak.",
                    )

                # Send media to user
                await self.telegram_service.send_media_result(
                    chat_id=telegram_id,
                    media=media_result,
                    status_message_id=status_message_id,
                )

                # Update database: completed
                async with get_db_session() as session:
                    await JobRepository.update_status(session, job_id, "completed")
                logger.info(f"Job {job_id} completed successfully for user {telegram_id}")

        except JobCancelledError:
            logger.info(f"Job {job_id} cancelled.")
            async with get_db_session() as session:
                await JobRepository.update_status(session, job_id, "cancelled")
            if status_message_id:
                await self.telegram_service.edit_status_text(
                    chat_id=telegram_id,
                    message_id=status_message_id,
                    text="❌ <b>Pengunduhan dibatalkan.</b>",
                )
        except AppError as e:
            logger.warning(f"Job {job_id} failed with AppError: {e}")
            async with get_db_session() as session:
                await JobRepository.update_status(
                    session=session,
                    job_id=job_id,
                    status="failed",
                    error_message=str(e),
                )
            if status_message_id:
                await self.telegram_service.edit_status_text(
                    chat_id=telegram_id,
                    message_id=status_message_id,
                    text=f"❌ <b>Gagal Mengunduh</b>\n\n{e.user_message}",
                )
        except Exception as e:
            logger.error(f"Job {job_id} encountered unhandled exception: {e}", exc_info=True)
            async with get_db_session() as session:
                await JobRepository.update_status(
                    session=session,
                    job_id=job_id,
                    status="failed",
                    error_message=str(e),
                )
            if status_message_id:
                await self.telegram_service.edit_status_text(
                    chat_id=telegram_id,
                    message_id=status_message_id,
                    text="❌ Maaf, video belum berhasil diunduh. Tautan ini mungkin tidak didukung atau kontennya tidak bisa diakses.",
                )
        finally:
            if progress_task and not progress_task.done():
                progress_task.cancel()
            await job_manager.unregister(job_id)
            clean_job_directory(job_dir)

    async def _periodic_status_updater(
        self,
        telegram_id: int,
        status_message_id: int,
        tracker: DownloadProgressTracker,
        title: str,
    ) -> None:
        """Periodically update Telegram status message with throttled download progress."""
        last_rendered_text = ""
        while not tracker.is_cancelled:
            await asyncio.sleep(2.5)
            state = tracker.current_state

            if state.status == "downloading":
                bar = state.render_telegram_progress_bar()
                text = (
                    f"⬇️ <b>Mengunduh:</b> {title[:40]}\n\n"
                    f"<code>{bar}</code>\n"
                    f"📊 <b>Ukuran:</b> {state.formatted_progress}\n"
                    f"⚡️ <b>Kecepatan:</b> {state.formatted_speed}\n"
                    f"⏱ <b>Estimasi:</b> {state.formatted_eta}"
                )
            elif state.status == "processing":
                text = (
                    f"⚙️ <b>Memproses Media:</b> {title[:40]}\n\n"
                    "Menggabungkan audio dan video dengan FFmpeg..."
                )
            else:
                continue

            if text != last_rendered_text:
                success = await self.telegram_service.edit_status_text(
                    chat_id=telegram_id,
                    message_id=status_message_id,
                    text=text,
                )
                if success:
                    last_rendered_text = text
